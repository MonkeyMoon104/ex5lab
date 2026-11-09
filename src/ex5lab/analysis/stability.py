"""Ephemeral vs content-bearing byte atlas for unprotected EX5 builds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ex5lab.binary.hashing import sha256_hex
from ex5lab.binary.validation import validate_and_read


def _collapse_offsets(offsets: list[int]) -> list[dict[str, int]]:
    if not offsets:
        return []
    regions: list[dict[str, int]] = []
    start = prev = offsets[0]
    for off in offsets[1:]:
        if off == prev + 1:
            prev = off
            continue
        regions.append({"start": start, "end": prev, "length": prev - start + 1})
        start = prev = off
    regions.append({"start": start, "end": prev, "length": prev - start + 1})
    return regions


def build_stability_atlas(paths: list[str | Path]) -> dict[str, Any]:
    """Compute intersection of identical bytes across >=2 builds of the same source.

    Returns stable/unstable masks over the minimum overlapping length.
    """
    if len(paths) < 2:
        raise ValueError("Need at least 2 builds for a stability atlas")

    loaded = []
    for p in paths:
        v = validate_and_read(p)
        loaded.append({"path": str(v.path), "size": v.size, "sha256": sha256_hex(v.data), "data": v.data})

    sizes = [x["size"] for x in loaded]
    min_len = min(sizes)
    max_len = max(sizes)
    hashes = [x["sha256"] for x in loaded]
    unique_hashes = len(set(hashes))

    stable_offsets: list[int] = []
    unstable_offsets: list[int] = []
    for i in range(min_len):
        values = {item["data"][i] for item in loaded}
        if len(values) == 1:
            stable_offsets.append(i)
        else:
            unstable_offsets.append(i)

    # Size-tail beyond min_len is ephemeral/size-noise by definition for atlas purposes
    trailing = None
    if max_len > min_len:
        trailing = {"start": min_len, "end": max_len - 1, "length": max_len - min_len}

    stable_regions = _collapse_offsets(stable_offsets)
    unstable_regions = _collapse_offsets(unstable_offsets)

    # Canonical stable mask bytes (from first build) for hashing of content-bearing view
    ref = loaded[0]["data"]
    stable_bytes = bytes(ref[i] for i in stable_offsets)
    unstable_sample = [
        {
            "offset": off,
            "values": sorted({f"{item['data'][off]:02x}" for item in loaded}),
        }
        for off in unstable_offsets[:64]
    ]

    return {
        "tool": "ex5lab.analysis.stability",
        "phase": "2",
        "n_builds": len(loaded),
        "builds": [{"path": x["path"], "size_bytes": x["size"], "sha256": x["sha256"]} for x in loaded],
        "unique_hashes": unique_hashes,
        "all_identical": unique_hashes == 1,
        "min_len": min_len,
        "max_len": max_len,
        "stable_byte_count": len(stable_offsets),
        "unstable_byte_count": len(unstable_offsets),
        "stable_fraction": round(len(stable_offsets) / min_len, 6) if min_len else 0.0,
        "stable_regions": stable_regions,
        "unstable_regions": unstable_regions[:256],
        "unstable_regions_truncated": len(unstable_regions) > 256,
        "trailing_size_span": trailing,
        "stable_mask_sha256": sha256_hex(stable_bytes),
        "stable_mask_length": len(stable_bytes),
        "sample_unstable_offsets": unstable_sample,
        "prefix32_hex": ref[:32].hex(" ") if min_len >= 32 else ref.hex(" "),
        "prefix32_stable": all(i in set(stable_offsets) for i in range(min(32, min_len))),
        "evidence_note": (
            "Stable bytes are identical across the listed rebuilds only. "
            "They are not proven instruction boundaries."
        ),
        # Compact mask for reuse: list of stable offsets (may be large; kept for research)
        "stable_offsets": stable_offsets,
    }


def apply_stable_mask(data: bytes, stable_offsets: list[int]) -> bytes:
    """Extract only stable-offset bytes (noise-controlled representation)."""
    return bytes(data[i] for i in stable_offsets if i < len(data))


def compare_on_stable_mask(
    path_a: str | Path,
    path_b: str | Path,
    stable_offsets: list[int],
) -> dict[str, Any]:
    """Compare two binaries restricted to a previously computed stable-offset mask."""
    a = validate_and_read(path_a)
    b = validate_and_read(path_b)
    sa = apply_stable_mask(a.data, stable_offsets)
    sb = apply_stable_mask(b.data, stable_offsets)
    min_len = min(len(sa), len(sb))
    matching = sum(1 for i in range(min_len) if sa[i] == sb[i])
    differing = [
        {"mask_index": i, "offset": stable_offsets[i], "a": f"{sa[i]:02x}", "b": f"{sb[i]:02x}"}
        for i in range(min_len)
        if sa[i] != sb[i]
    ]
    return {
        "tool": "ex5lab.analysis.compare_on_stable_mask",
        "phase": "2",
        "path_a": str(a.path),
        "path_b": str(b.path),
        "sha256_a": sha256_hex(a.data),
        "sha256_b": sha256_hex(b.data),
        "stable_mask_len": len(stable_offsets),
        "stable_view_sha256_a": sha256_hex(sa),
        "stable_view_sha256_b": sha256_hex(sb),
        "stable_views_identical": sa == sb,
        "matching_stable_bytes": matching,
        "differing_stable_bytes": len(differing),
        "sample_diffs": differing[:64],
        "sample_diffs_truncated": len(differing) > 64,
        "research_disclaimer": (
            "Differences on the stable mask exclude rebuild-ephemeral offsets from the "
            "atlas used to define the mask. They still do not prove instruction semantics."
        ),
    }
