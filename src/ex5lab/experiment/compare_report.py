"""Baseline/variant comparison reports with hashes and region stats."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ex5lab.binary.compare import compare_binaries
from ex5lab.binary.hashing import sha256_hex
from ex5lab.binary.sliding import sliding_window_stats
from ex5lab.binary.similarity import robust_similarity
from ex5lab.binary.validation import validate_and_read


def build_differential_report(
    path_a: str | Path,
    path_b: str | Path,
    *,
    label_a: str = "baseline",
    label_b: str = "variant",
    source_a_sha256: str | None = None,
    source_b_sha256: str | None = None,
    include_sliding: bool = True,
) -> dict[str, Any]:
    """Full Phase-1 style comparison with shift-aware metrics."""
    a = validate_and_read(path_a)
    b = validate_and_read(path_b)
    basic = compare_binaries(str(a.path), str(b.path), include_per_file_inspect=False)
    robust = robust_similarity(a.data, b.data)
    report: dict[str, Any] = {
        "tool": "ex5lab.experiment.compare_report",
        "phase": "1",
        "label_a": label_a,
        "label_b": label_b,
        "source_sha256_a": source_a_sha256,
        "source_sha256_b": source_b_sha256,
        "binary_a": {
            "path": str(a.path),
            "sha256": sha256_hex(a.data),
            "size_bytes": a.size,
        },
        "binary_b": {
            "path": str(b.path),
            "sha256": sha256_hex(b.data),
            "size_bytes": b.size,
        },
        "aligned_compare": basic,
        "robust_similarity": robust,
        "research_disclaimer": (
            "Byte differences are observations. They do not by themselves prove "
            "instruction mappings or MQL5 construct locations."
        ),
    }
    if include_sliding:
        report["sliding_a"] = sliding_window_stats(a.data)
        report["sliding_b"] = sliding_window_stats(b.data)
        # Compact: drop full window arrays from default report to keep JSON usable
        report["sliding_a"] = {
            "summary": report["sliding_a"]["summary"],
            "window": report["sliding_a"]["window"],
            "stride": report["sliding_a"]["stride"],
            "count": report["sliding_a"]["count"],
        }
        report["sliding_b"] = {
            "summary": report["sliding_b"]["summary"],
            "window": report["sliding_b"]["window"],
            "stride": report["sliding_b"]["stride"],
            "count": report["sliding_b"]["count"],
        }
    return report
