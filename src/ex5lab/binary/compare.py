"""Binary comparison without semantic claims about MQL5 constructs."""

from __future__ import annotations

from typing import Any

from ex5lab.binary.hashing import sha256_hex
from ex5lab.binary.inspect import inspect_file
from ex5lab.binary.validation import DEFAULT_MAX_BYTES, validate_and_read


def _regions_from_mask(equal: list[bool]) -> tuple[list[dict[str, int]], list[dict[str, int]]]:
    """Collapse a boolean equality mask into contiguous common/differing regions."""
    common: list[dict[str, int]] = []
    differing: list[dict[str, int]] = []
    if not equal:
        return common, differing

    start = 0
    current = equal[0]
    for i in range(1, len(equal)):
        if equal[i] != current:
            region = {"start": start, "end": i - 1, "length": i - start}
            (common if current else differing).append(region)
            start = i
            current = equal[i]
    region = {"start": start, "end": len(equal) - 1, "length": len(equal) - start}
    (common if current else differing).append(region)
    return common, differing


def compare_binaries(
    path_a: str,
    path_b: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_diff_offsets: int = 64,
    max_regions: int = 128,
    include_per_file_inspect: bool = True,
) -> dict[str, Any]:
    """Compare two binaries and report structural byte-level differences.

    Similarity metrics are descriptive only. Differing regions are NOT claimed
    to represent specific MQL5 language constructs.
    """
    a = validate_and_read(path_a, max_bytes=max_bytes)
    b = validate_and_read(path_b, max_bytes=max_bytes)

    data_a, data_b = a.data, b.data
    min_len = min(len(data_a), len(data_b))
    max_len = max(len(data_a), len(data_b))
    size_delta = len(data_b) - len(data_a)

    equal_mask = [data_a[i] == data_b[i] for i in range(min_len)]
    matching = sum(1 for v in equal_mask if v)
    differing_count = min_len - matching

    common_regions, differing_regions = _regions_from_mask(equal_mask)

    # Trailing size mismatch is an additional differing span beyond min_len.
    trailing: dict[str, Any] | None = None
    if len(data_a) != len(data_b):
        longer = "a" if len(data_a) > len(data_b) else "b"
        trailing = {
            "start": min_len,
            "end": max_len - 1,
            "length": max_len - min_len,
            "present_only_in": longer,
        }

    diff_offsets: list[dict[str, Any]] = []
    for i, same in enumerate(equal_mask):
        if same:
            continue
        diff_offsets.append(
            {
                "offset": i,
                "a": f"{data_a[i]:02x}",
                "b": f"{data_b[i]:02x}",
            }
        )
        if len(diff_offsets) >= max_diff_offsets:
            break

    # Jaccard over byte multiset is expensive; use simple set Jaccard + normalized Hamming.
    set_a = set(data_a)
    set_b = set(data_b)
    union = set_a | set_b
    inter = set_a & set_b
    jaccard = (len(inter) / len(union)) if union else 1.0
    overlap_ratio = (matching / min_len) if min_len else 1.0
    # Normalized edit-agnostic similarity in [0,1]: matching bytes over max length.
    byte_similarity = (matching / max_len) if max_len else 1.0

    identical = data_a == data_b

    report: dict[str, Any] = {
        "tool": "ex5lab.compare",
        "phase": "0",
        "a": {
            "path": str(a.path),
            "size_bytes": a.size,
            "sha256": sha256_hex(data_a),
        },
        "b": {
            "path": str(b.path),
            "size_bytes": b.size,
            "sha256": sha256_hex(data_b),
        },
        "identical": identical,
        "size_delta_b_minus_a": size_delta,
        "overlap_length": min_len,
        "matching_bytes": matching,
        "differing_bytes_in_overlap": differing_count,
        "metrics": {
            "byte_similarity": round(byte_similarity, 6),
            "overlap_equal_ratio": round(overlap_ratio, 6),
            "unique_byte_jaccard": round(jaccard, 6),
            "notes": (
                "Metrics are descriptive binary similarity scores only. "
                "They do not identify MQL5 constructs, optimization effects, "
                "or EX5 section boundaries."
            ),
        },
        "common_regions": common_regions[:max_regions],
        "differing_regions": differing_regions[:max_regions],
        "regions_truncated": (
            len(common_regions) > max_regions or len(differing_regions) > max_regions
        ),
        "trailing_size_mismatch": trailing,
        "sample_diff_offsets": diff_offsets,
        "sample_diff_offsets_truncated": differing_count > max_diff_offsets,
        "research_disclaimer": (
            "Region boundaries are byte-equality collapses, not parsed EX5 sections. "
            "Do not interpret diffs as specific MQL5 AST/construct changes without "
            "controlled experiments."
        ),
    }

    if include_per_file_inspect:
        report["per_file_summary"] = {
            "a": {
                "size_bytes": a.size,
                "sha256": report["a"]["sha256"],
            },
            "b": {
                "size_bytes": b.size,
                "sha256": report["b"]["sha256"],
            },
            "full_inspect_available_via": "ex5lab inspect <file>",
        }

    return report


def compare_with_optional_inspect(
    path_a: str,
    path_b: str,
    *,
    deep_inspect: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compare and optionally attach abbreviated inspect reports."""
    report = compare_binaries(path_a, path_b, **kwargs)
    if deep_inspect:
        report["inspect_a"] = inspect_file(path_a)
        report["inspect_b"] = inspect_file(path_b)
    return report
