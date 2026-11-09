"""Repeated-build consistency measurements."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ex5lab.binary.hashing import sha256_hex
from ex5lab.binary.similarity import robust_similarity
from ex5lab.binary.validation import validate_and_read


def pairwise_consistency(paths: list[str | Path]) -> dict[str, Any]:
    """Measure hash/size agreement and pairwise similarity across builds."""
    if len(paths) < 2:
        raise ValueError("Need at least two builds for consistency analysis")

    loaded = []
    for p in paths:
        v = validate_and_read(p)
        loaded.append(
            {
                "path": str(v.path),
                "size_bytes": v.size,
                "sha256": sha256_hex(v.data),
                "data": v.data,
            }
        )

    hashes = [x["sha256"] for x in loaded]
    sizes = [x["size_bytes"] for x in loaded]
    hash_counts = Counter(hashes)
    unique_hashes = len(hash_counts)
    all_identical = unique_hashes == 1
    all_same_size = len(set(sizes)) == 1

    pairs: list[dict[str, Any]] = []
    for i in range(len(loaded)):
        for j in range(i + 1, len(loaded)):
            sim = robust_similarity(loaded[i]["data"], loaded[j]["data"])
            # Drop raw-heavy nested detail for pair list compactness where useful
            pairs.append(
                {
                    "a": loaded[i]["path"],
                    "b": loaded[j]["path"],
                    "identical": loaded[i]["sha256"] == loaded[j]["sha256"],
                    "aligned_byte_similarity": sim["aligned_byte_similarity"],
                    "fingerprint_jaccard": sim["fingerprint_jaccard"]["jaccard"],
                    "sequence_matcher_ratio": sim["sequence_matcher"].get("ratio"),
                }
            )

    # Locate byte positions that vary across builds (union of pairwise diffs in overlap)
    min_len = min(sizes)
    unstable_offsets: list[int] = []
    if min_len > 0 and not all_identical:
        for off in range(min_len):
            values = {item["data"][off] for item in loaded}
            if len(values) > 1:
                unstable_offsets.append(off)

    # Collapse unstable offsets into regions
    regions: list[dict[str, int]] = []
    if unstable_offsets:
        start = prev = unstable_offsets[0]
        for off in unstable_offsets[1:]:
            if off == prev + 1:
                prev = off
                continue
            regions.append({"start": start, "end": prev, "length": prev - start + 1})
            start = prev = off
        regions.append({"start": start, "end": prev, "length": prev - start + 1})

    return {
        "n_builds": len(loaded),
        "all_identical": all_identical,
        "all_same_size": all_same_size,
        "unique_hashes": unique_hashes,
        "hash_histogram": dict(hash_counts),
        "builds": [
            {"path": x["path"], "size_bytes": x["size_bytes"], "sha256": x["sha256"]}
            for x in loaded
        ],
        "pairwise": pairs,
        "unstable_byte_count_in_overlap": len(unstable_offsets),
        "unstable_regions": regions[:128],
        "unstable_regions_truncated": len(regions) > 128,
        "sample_unstable_offsets": unstable_offsets[:64],
        "classification": (
            "deterministic_under_tested_conditions"
            if all_identical
            else "non_deterministic_or_noisy_under_tested_conditions"
        ),
        "evidence_note": (
            "Consistency is measured only for the recorded builds and settings. "
            "Do not generalize beyond the experiment matrix."
        ),
    }
