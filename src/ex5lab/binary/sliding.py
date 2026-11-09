"""Sliding-window entropy and region statistics (read-only)."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any


def _shannon(data: bytes) -> float:
    if not data:
        return 0.0
    n = len(data)
    counts = Counter(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def sliding_window_stats(
    data: bytes,
    *,
    window: int = 256,
    stride: int = 64,
    max_windows: int = 4096,
) -> dict[str, Any]:
    """Compute per-window entropy and zero-byte density.

    Complexity is O(n) over the file for fixed window/stride.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if stride < 1:
        raise ValueError("stride must be >= 1")

    windows: list[dict[str, Any]] = []
    if not data:
        return {
            "window": window,
            "stride": stride,
            "count": 0,
            "windows": [],
            "summary": {
                "mean_entropy": 0.0,
                "min_entropy": 0.0,
                "max_entropy": 0.0,
                "mean_zero_fraction": 0.0,
            },
            "truncated": False,
        }

    truncated = False
    for start in range(0, len(data), stride):
        chunk = data[start : start + window]
        if not chunk:
            break
        ent = _shannon(chunk)
        zeros = chunk.count(0)
        windows.append(
            {
                "offset": start,
                "length": len(chunk),
                "entropy": round(ent, 6),
                "zero_fraction": round(zeros / len(chunk), 6),
            }
        )
        if len(windows) >= max_windows:
            truncated = True
            break

    ents = [w["entropy"] for w in windows]
    zfs = [w["zero_fraction"] for w in windows]
    return {
        "window": window,
        "stride": stride,
        "count": len(windows),
        "windows": windows,
        "summary": {
            "mean_entropy": round(sum(ents) / len(ents), 6) if ents else 0.0,
            "min_entropy": round(min(ents), 6) if ents else 0.0,
            "max_entropy": round(max(ents), 6) if ents else 0.0,
            "mean_zero_fraction": round(sum(zfs) / len(zfs), 6) if zfs else 0.0,
        },
        "truncated": truncated,
        "evidence_note": (
            "Descriptive window statistics only; not EX5 section boundaries."
        ),
    }
