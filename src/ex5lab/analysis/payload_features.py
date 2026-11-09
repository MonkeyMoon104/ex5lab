"""Post-header / metadata feature extraction .

Exclusion windows are heuristics  -  not proven executable-payload boundaries.
Feature families must not mislabel size leakage as metadata-only.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

from ex5lab.analysis.eval_design import INVALID_EVALUATION_DESIGN, SampleRow, validate_loo_feasibility
from ex5lab.binary.hashing import sha256_hex
from ex5lab.binary.validation import validate_and_read

DEFAULT_METADATA_EXCLUSION_END = 744

FEATURE_FAMILIES = (
    "size_only",
    "verified_metadata_fields",
    "header_stats_only",
    "post_header_raw",
    "post_header_size_excluded",
    "post_header_standardized_combo",
    "metadata_inclusive_full",  # diagnostic only
)


def shannon(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def extract_payload_features(
    path: str | Path,
    *,
    metadata_exclusion_end: int = DEFAULT_METADATA_EXCLUSION_END,
    chunk_size: int = 64,
) -> dict[str, Any]:
    v = validate_and_read(path)
    data = v.data
    size = len(data)
    excl = min(metadata_exclusion_end, size)
    payload = data[excl:]
    header = data[:excl]
    full_ent = shannon(data)
    pay_ent = shannon(payload)
    hdr_ent = shannon(header)

    def chunk_ents(buf: bytes) -> list[float]:
        if not buf:
            return []
        return [round(shannon(buf[i : i + chunk_size]), 6) for i in range(0, len(buf), chunk_size)]

    pay_chunks = chunk_ents(payload)
    mean_ce = sum(pay_chunks) / len(pay_chunks) if pay_chunks else 0.0
    var_ce = sum((x - mean_ce) ** 2 for x in pay_chunks) / len(pay_chunks) if pay_chunks else 0.0
    hist = [0] * 256
    for b in payload:
        hist[b] += 1
    bins16 = [sum(hist[i * 16 : (i + 1) * 16]) for i in range(16)]
    total = max(1, len(payload))
    bins16_norm = [round(x / total, 8) for x in bins16]
    byte3 = f"{data[3]:02x}" if len(data) > 3 else None

    # Lightweight UTF-16LE ASCII strings in header window for verified metadata-ish fields
    meta_strings = []
    i = 0
    while i + 3 < excl:
        if 32 <= data[i] <= 126 and data[i + 1] == 0:
            chars = []
            j = i
            while j + 1 < excl and 32 <= data[j] <= 126 and data[j + 1] == 0:
                chars.append(chr(data[j]))
                j += 2
            if len(chars) >= 2:
                meta_strings.append("".join(chars))
                i = j
                continue
        i += 1

    return {
        "path": str(v.path),
        "sha256": sha256_hex(data),
        "size_bytes": size,
        "metadata_exclusion_end": excl,
        "exclusion_label": "post_header_heuristic_not_verified_payload",
        "payload_bytes": len(payload),
        "header_bytes": len(header),
        "full_entropy": round(full_ent, 6),
        "header_entropy": round(hdr_ent, 6),
        "payload_entropy": round(pay_ent, 6),
        "payload_chunk_entropy_mean": round(mean_ce, 6),
        "payload_chunk_entropy_var": round(var_ce, 6),
        "payload_bins16": bins16_norm,
        "byte3_hex": byte3,
        "header_utf16le_strings": meta_strings[:32],
        "alignment_policy": (
            f"exclude_[0,{excl}) heuristic; feature families documented separately; "
            "do not treat as ISA decode"
        ),
    }


def feature_vector_family(feat: dict[str, Any], family: str) -> list[float]:
    bins = list(feat.get("payload_bins16") or [0.0] * 16)
    if family == "size_only":
        return [float(feat["size_bytes"])]
    if family == "verified_metadata_fields":
        # Decoded-ish: byte3 + lengths of first few UTF16 strings + count  -  NO total size_bytes
        b3 = int(feat["byte3_hex"], 16) if feat.get("byte3_hex") else -1
        strs = feat.get("header_utf16le_strings") or []
        lens = [float(len(s)) for s in strs[:4]]
        while len(lens) < 4:
            lens.append(0.0)
        return [float(b3), float(len(strs)), *lens]
    if family == "header_stats_only":
        # Header window stats only  -  NO total file size
        b3 = int(feat["byte3_hex"], 16) if feat.get("byte3_hex") else -1
        return [
            float(feat["header_bytes"]),
            float(feat["header_entropy"]),
            float(b3),
        ]
    if family == "metadata_only_header":
        # Deprecated alias: now equals header_stats_only (Director correction  -  no size leak)
        return feature_vector_family(feat, "header_stats_only")
    if family == "metadata_inclusive_full":
        return [
            float(feat["size_bytes"]),
            float(feat["full_entropy"]),
            float(feat["payload_bytes"]),
            float(feat["payload_entropy"]),
            *bins,
        ]
    if family == "post_header_raw":
        return [
            float(feat["payload_bytes"]),
            float(feat["payload_entropy"]),
            float(feat["payload_chunk_entropy_mean"]),
            float(feat["payload_chunk_entropy_var"]),
            *bins,
        ]
    if family == "post_header_size_excluded":
        return [
            float(feat["payload_entropy"]),
            float(feat["payload_chunk_entropy_mean"]),
            float(feat["payload_chunk_entropy_var"]),
            *bins,
        ]
    if family == "post_header_standardized_combo":
        return [
            float(feat["payload_bytes"]),
            float(feat["payload_entropy"]),
            float(feat["payload_chunk_entropy_mean"]),
            float(feat["payload_chunk_entropy_var"]),
            *bins,
        ]
    raise ValueError(f"unknown feature family: {family}")


def feature_vector(feat: dict[str, Any], *, ablate_metadata: bool = True) -> list[float]:
    if ablate_metadata:
        return feature_vector_family(feat, "post_header_raw")
    return feature_vector_family(feat, "metadata_inclusive_full")


def l2(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(n)))


def nearest_neighbor_accuracy(
    labels: list[str],
    features: list[dict[str, Any]],
    *,
    ablate_metadata: bool = True,
    leave_one_out: bool = True,
    group_ids: list[str] | None = None,
) -> dict[str, Any]:
    if len(labels) != len(features) or len(labels) < 2:
        return {"ok": False, "status": INVALID_EVALUATION_DESIGN, "reason": "need >=2 labeled samples"}
    gids = group_ids or [f"g{i}_{labels[i]}" for i in range(len(labels))]
    rows = [
        SampleRow(f"s{i}", gids[i], labels[i], features[i]) for i in range(len(labels))
    ]
    check = validate_loo_feasibility(rows)
    if leave_one_out and not check["ok"]:
        return {
            "ok": False,
            "status": INVALID_EVALUATION_DESIGN,
            "accuracy": None,
            "design_check": check,
            "note": "Refusing structurally forced 0% LOO headline.",
        }
    vecs = [feature_vector(f, ablate_metadata=ablate_metadata) for f in features]
    correct = 0
    preds = []
    for i in range(len(vecs)):
        best_j = None
        best_d = float("inf")
        for j in range(len(vecs)):
            if leave_one_out and i == j:
                continue
            if gids[i] == gids[j]:
                continue
            d = l2(vecs[i], vecs[j])
            if d < best_d:
                best_d = d
                best_j = j
        pred = labels[best_j] if best_j is not None else None
        preds.append(pred)
        if pred == labels[i]:
            correct += 1
    if any(p is None for p in preds):
        return {"ok": False, "status": INVALID_EVALUATION_DESIGN, "reason": "no eligible neighbor"}
    acc = correct / len(labels)
    counts = Counter(labels)
    majority = counts.most_common(1)[0][1] / len(labels)
    return {
        "ok": True,
        "status": "OK",
        "n": len(labels),
        "accuracy": round(acc, 4),
        "correct": correct,
        "predictions": preds,
        "majority_chance": round(majority, 4),
        "deprecated_api": True,
    }