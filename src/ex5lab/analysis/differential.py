"""Pairwise EX5 / binary differential helpers .

Reports descriptive byte-level deltas only. Candidate explanations are
hypotheses  -  never claimed as proven opcode semantics.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from pathlib import Path
from typing import Any

from ex5lab.analysis.sequence import longest_common_substring_naive


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    n = len(data)
    counts = Counter(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def hamming_and_byte_diffs(
    a: bytes,
    b: bytes,
    *,
    max_offsets: int = 256,
) -> dict[str, Any]:
    n = min(len(a), len(b))
    diffs: list[dict[str, Any]] = []
    differing = 0
    for i in range(n):
        if a[i] != b[i]:
            differing += 1
            if len(diffs) < max_offsets:
                diffs.append({"offset": i, "a": f"{a[i]:02x}", "b": f"{b[i]:02x}"})
    return {
        "overlap_bytes": n,
        "hamming_distance": differing,
        "hamming_ratio": (differing / n) if n else 0.0,
        "size_delta_b_minus_a": len(b) - len(a),
        "diff_offsets_sample": diffs,
        "diff_offsets_truncated": differing > max_offsets,
    }


def entropy_windows(data: bytes, *, window: int = 64) -> list[dict[str, Any]]:
    if window <= 0:
        raise ValueError("window must be > 0")
    out: list[dict[str, Any]] = []
    for i in range(0, len(data), window):
        chunk = data[i : i + window]
        out.append(
            {
                "start": i,
                "end": i + len(chunk),
                "entropy": round(shannon_entropy(chunk), 6),
                "size": len(chunk),
            }
        )
    return out


def lcs_bounded(
    a: bytes,
    b: bytes,
    *,
    max_product: int = 2_000_000,
    max_scan: int = 8_000,
) -> dict[str, Any]:
    """Longest common *substring* length with hard budget (descriptive only)."""
    return longest_common_substring_naive(
        a,
        b,
        max_product=max_product,
        allow_truncate=True,
        max_scan=max_scan,
    )


def pairwise_compare(
    path_a: str | Path,
    path_b: str | Path,
    *,
    source_change: dict[str, Any] | None = None,
    behavior_note: str | None = None,
    max_diff_offsets: int = 256,
    entropy_window: int = 64,
    header_heuristic: int = 744,
) -> dict[str, Any]:
    """Compare two binaries and emit the differential report schema.

    Schema layers:
      SOURCE_CHANGE -> BEHAVIOR -> BINARY_DELTA -> CANDIDATE_EXPLANATION
    """
    pa, pb = Path(path_a), Path(path_b)
    data_a = pa.read_bytes()
    data_b = pb.read_bytes()

    byte_delta = hamming_and_byte_diffs(data_a, data_b, max_offsets=max_diff_offsets)
    lcs = lcs_bounded(data_a, data_b)
    ent_a = entropy_windows(data_a, window=entropy_window)
    ent_b = entropy_windows(data_b, window=entropy_window)

    hdr = min(header_heuristic, len(data_a), len(data_b))
    header_same = data_a[:hdr] == data_b[:hdr] if hdr else True

    # Hypothesis scaffolding  -  never asserted as proven decode.
    candidates: list[dict[str, Any]] = []
    if data_a == data_b:
        candidates.append(
            {
                "id": "identical_bytes",
                "confidence": "descriptive",
                "text": "Byte-identical inputs; no binary delta to explain.",
                "evidence": "sha256_equal",
            }
        )
    else:
        if byte_delta["hamming_distance"] == 0 and byte_delta["size_delta_b_minus_a"] != 0:
            candidates.append(
                {
                    "id": "length_only_delta",
                    "confidence": "hypothesis",
                    "text": "Overlap bytes match; size differs (append/truncate hypothesis).",
                    "evidence": "hamming_zero_with_size_delta",
                }
            )
        if header_same and byte_delta["hamming_distance"] > 0:
            candidates.append(
                {
                    "id": "post_header_delta",
                    "confidence": "hypothesis",
                    "text": (
                        f"First {hdr} bytes match (heuristic header window); "
                        "diffs appear after that window. Not a proven section map."
                    ),
                    "evidence": "header_heuristic_equal",
                }
            )
        if not header_same:
            candidates.append(
                {
                    "id": "early_byte_delta",
                    "confidence": "hypothesis",
                    "text": (
                        f"Differences within first {hdr} bytes (heuristic). "
                        "May include metadata or format fields  -  unverified."
                    ),
                    "evidence": "header_heuristic_diff",
                }
            )
        candidates.append(
            {
                "id": "opaque_byte_delta",
                "confidence": "unknown",
                "text": (
                    "Remaining deltas are opaque without a verified ISA map. "
                    "No EX5 opcode explanation is asserted."
                ),
                "evidence": "no_opcode_decoder",
            }
        )

    return {
        "schema": "phase10_differential_report_v1",
        "SOURCE_CHANGE": source_change
        or {
            "status": "unspecified",
            "note": "Caller should describe MQ5/source delta when known.",
        },
        "BEHAVIOR": {
            "note": behavior_note
            or "Behavior not executed in this helper; supply from experiment notes.",
            "live_trading": False,
        },
        "BINARY_DELTA": {
            "a": {
                "path": str(pa),
                "size": len(data_a),
                "sha256": sha256_bytes(data_a),
                "entropy": round(shannon_entropy(data_a), 6),
            },
            "b": {
                "path": str(pb),
                "size": len(data_b),
                "sha256": sha256_bytes(data_b),
                "entropy": round(shannon_entropy(data_b), 6),
            },
            "identical": data_a == data_b,
            "byte_diff": byte_delta,
            "lcs_bounded": lcs,
            "entropy_windows": {"a": ent_a[:32], "b": ent_b[:32], "window": entropy_window},
            "header_heuristic_bytes": hdr,
            "header_heuristic_identical": header_same,
        },
        "CANDIDATE_EXPLANATION": {
            "candidates": candidates,
            "disclaimer": (
                "Candidates are research hypotheses only. "
                "They are not proven EX5 semantic mappings."
            ),
        },
    }
