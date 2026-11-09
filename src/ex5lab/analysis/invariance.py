"""Nondeterminism-aware EX5 population comparison .

Compares populations of builds, not only single A-vs-B pairs. Does not claim
that stable bytes are executable instructions.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    n = len(data)
    counts = Counter(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def common_prefix_len(blobs: Iterable[bytes]) -> int:
    seq = list(blobs)
    if not seq:
        return 0
    prefix = 0
    while True:
        if any(len(b) <= prefix for b in seq):
            return prefix
        v = seq[0][prefix]
        if any(b[prefix] != v for b in seq[1:]):
            return prefix
        prefix += 1


def stable_mask(blobs: list[bytes]) -> dict[str, Any]:
    """Bytes identical across all builds on the min shared length."""
    if not blobs:
        return {
            "n": 0,
            "min_len": 0,
            "stable_count": 0,
            "stable_fraction": 0.0,
            "stable_offsets": [],
            "variable_offsets_sample": [],
        }
    min_len = min(len(b) for b in blobs)
    stable: list[int] = []
    variable: list[int] = []
    for i in range(min_len):
        v = blobs[0][i]
        if all(b[i] == v for b in blobs[1:]):
            stable.append(i)
        else:
            variable.append(i)
    return {
        "n": len(blobs),
        "min_len": min_len,
        "max_len": max(len(b) for b in blobs),
        "size_set": sorted({len(b) for b in blobs}),
        "stable_count": len(stable),
        "variable_count": len(variable),
        "stable_fraction": (len(stable) / min_len) if min_len else 0.0,
        "stable_offsets_sample": stable[:64],
        "variable_offsets_sample": variable[:64],
        "common_prefix_len": common_prefix_len(blobs),
    }


def pairwise_hamming(blobs: list[bytes]) -> dict[str, Any]:
    ratios: list[float] = []
    distances: list[int] = []
    for i in range(len(blobs)):
        for j in range(i + 1, len(blobs)):
            a, b = blobs[i], blobs[j]
            n = min(len(a), len(b))
            dist = sum(1 for k in range(n) if a[k] != b[k])
            distances.append(dist)
            ratios.append(dist / n if n else 0.0)
    if not ratios:
        return {"n_pairs": 0, "hamming_ratio_mean": None, "hamming_ratio_min": None, "hamming_ratio_max": None}
    return {
        "n_pairs": len(ratios),
        "hamming_ratio_mean": sum(ratios) / len(ratios),
        "hamming_ratio_min": min(ratios),
        "hamming_ratio_max": max(ratios),
        "hamming_distance_mean": sum(distances) / len(distances),
    }


def position_variability(blobs: list[bytes], *, max_positions: int = 4096) -> list[dict[str, Any]]:
    """Unique-byte count per offset for first max_positions of min length."""
    if not blobs:
        return []
    min_len = min(len(b) for b in blobs)
    lim = min(min_len, max_positions)
    out: list[dict[str, Any]] = []
    for i in range(lim):
        uniq = {b[i] for b in blobs}
        if len(uniq) > 1:
            out.append({"offset": i, "unique_values": len(uniq)})
    return out


def compare_populations(
    within: list[bytes],
    between: list[bytes],
    *,
    label_within: str = "identical_source",
    label_between: str = "semantic_or_control",
) -> dict[str, Any]:
    """Contrast within-source rebuild noise vs a second population.

    Does **not** claim the residual stable mask encodes executable ops.
    Avalanche / global re-layout may make aligned subtraction ineffective  - 
    that limitation is recorded explicitly.
    """
    w_mask = stable_mask(within)
    b_mask = stable_mask(between)
    w_ham = pairwise_hamming(within)
    b_ham = pairwise_hamming(between)
    # Intersection of stable offsets (same relative positions) on min lengths.
    if within and between:
        min_len = min(min(len(b) for b in within), min(len(b) for b in between))
        w_stable = set()
        for i in range(min_len):
            v = within[0][i]
            if all(x[i] == v for x in within[1:]):
                w_stable.add(i)
        b_stable = set()
        for i in range(min_len):
            v = between[0][i]
            if all(x[i] == v for x in between[1:]):
                b_stable.add(i)
        shared_stable = sorted(w_stable & b_stable)
        # Bytes that are stable within each population but differ between population means
        diverge: list[int] = []
        for i in shared_stable:
            if within[0][i] != between[0][i]:
                diverge.append(i)
    else:
        shared_stable = []
        diverge = []
        min_len = 0

    return {
        "schema": "phase11_population_compare_v1",
        "label_within": label_within,
        "label_between": label_between,
        "within": {
            "n": len(within),
            "unique_hashes": len({sha256_bytes(b) for b in within}),
            "entropy_mean": (
                sum(shannon_entropy(b) for b in within) / len(within) if within else None
            ),
            "stable_mask": w_mask,
            "pairwise_hamming": w_ham,
        },
        "between": {
            "n": len(between),
            "unique_hashes": len({sha256_bytes(b) for b in between}),
            "entropy_mean": (
                sum(shannon_entropy(b) for b in between) / len(between) if between else None
            ),
            "stable_mask": b_mask,
            "pairwise_hamming": b_ham,
        },
        "shared_stable_count": len(shared_stable),
        "shared_stable_but_value_differs_count": len(diverge),
        "shared_stable_value_diff_offsets_sample": diverge[:64],
        "analysis_scope": f"aligned_bytes_0_to_{min_len}",
        "avalanche_warning": (
            "If MetaEditor applies avalanche/encryption-like transforms, "
            "aligned-byte stable masks may not isolate executable semantics."
        ),
        "signal_vs_noise_note": (
            "A candidate mapping requires between-population divergence at "
            "positions that are stable within each population AND distinguishable "
            "from metadata/whitespace controls  -  not mere hash inequality."
        ),
    }


def load_ex5_dir(directory: Path, pattern: str = "*.ex5") -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for p in sorted(directory.glob(pattern)):
        out.append((p.name, p.read_bytes()))
    return out
