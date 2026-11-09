"""Reproducible EX5 pairwise binary segmentation (metadata research, not ISA)."""

from __future__ import annotations

from typing import Any


def equal_diff_runs(a: bytes, b: bytes) -> list[dict[str, Any]]:
    """Return contiguous EQ/DIFF intervals over the overlapping length."""
    n = min(len(a), len(b))
    runs: list[dict[str, Any]] = []
    i = 0
    while i < n:
        same = a[i] == b[i]
        j = i + 1
        while j < n and (a[j] == b[j]) == same:
            j += 1
        runs.append(
            {
                "kind": "EQ" if same else "DIFF",
                "start": i,
                "end_inclusive": j - 1,
                "length": j - i,
            }
        )
        i = j
    if len(a) != len(b):
        longer = "a" if len(a) > len(b) else "b"
        runs.append(
            {
                "kind": "LENGTH_TAIL",
                "start": n,
                "end_inclusive": max(len(a), len(b)) - 1,
                "length": abs(len(a) - len(b)),
                "longer": longer,
            }
        )
    return runs


def find_utf16le(data: bytes, text: str) -> int:
    return data.find(text.encode("utf-16le"))


def summarize_stable_windows(
    runs: list[dict[str, Any]], *, min_eq_length: int = 32
) -> list[dict[str, Any]]:
    return [r for r in runs if r.get("kind") == "EQ" and r["length"] >= min_eq_length]


def segment_pair(
    a: bytes,
    b: bytes,
    *,
    label_a: str = "a",
    label_b: str = "b",
    metadata_strings: list[str] | None = None,
) -> dict[str, Any]:
    runs = equal_diff_runs(a, b)
    meta = metadata_strings or []
    meta_hits = []
    for s in meta:
        off_a = find_utf16le(a, s)
        off_b = find_utf16le(b, s)
        meta_hits.append(
            {
                "text": s,
                "utf16le_offset_a": off_a,
                "utf16le_offset_b": off_b,
                "same_offset": off_a == off_b and off_a >= 0,
                "in_shared_eq_run": _offset_in_eq_run(off_a, runs) if off_a >= 0 else False,
            }
        )
    return {
        "schema": "ex5_pairwise_segmentation_v1",
        "label_a": label_a,
        "label_b": label_b,
        "size_a": len(a),
        "size_b": len(b),
        "shared_prefix_len": next(
            (r["length"] for r in runs if r.get("kind") == "EQ" and r.get("start") == 0),
            0,
        ),
        "runs": runs,
        "stable_eq_windows_ge32": summarize_stable_windows(runs, min_eq_length=32),
        "metadata_utf16le": meta_hits,
        "executable_isa_declared": False,
        "note": (
            "EQ/DIFF intervals are byte identity only. "
            "Stable regions may be metadata; DIFF regions are not proven executable code."
        ),
    }


def _offset_in_eq_run(offset: int, runs: list[dict[str, Any]]) -> bool:
    for r in runs:
        if r.get("kind") == "EQ" and r["start"] <= offset <= r["end_inclusive"]:
            return True
    return False


def region_overlap(start: int, end_inclusive: int, runs: list[dict[str, Any]], kind: str) -> int:
    """Count bytes of given kind overlapping [start, end_inclusive]."""
    total = 0
    for r in runs:
        if r.get("kind") != kind:
            continue
        lo = max(start, r["start"])
        hi = min(end_inclusive, r["end_inclusive"])
        if hi >= lo:
            total += hi - lo + 1
    return total
