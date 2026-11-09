"""Shift-aware binary similarity without O(n²) on large inputs."""

from __future__ import annotations

import hashlib
from typing import Any

# Soft threshold: SequenceMatcher is acceptable for small research EX5 files.
_SEQMATCH_MAX_BYTES = 256 * 1024


def window_fingerprints(
    data: bytes,
    *,
    window: int = 32,
    stride: int = 1,
) -> list[str]:
    """Fixed-window SHA-256 fingerprints (truncated to 16 hex chars)."""
    if window < 1 or stride < 1:
        raise ValueError("window and stride must be >= 1")
    out: list[str] = []
    if not data:
        return out
    for i in range(0, max(1, len(data) - window + 1), stride):
        chunk = data[i : i + window]
        digest = hashlib.sha256(chunk).hexdigest()[:16]
        out.append(digest)
        if i + window >= len(data):
            break
    # Ensure final window covering the tail when length not aligned
    if len(data) >= window:
        last = data[-window:]
        digest = hashlib.sha256(last).hexdigest()[:16]
        if not out or out[-1] != digest:
            out.append(digest)
    return out


def fingerprint_jaccard(
    a: bytes,
    b: bytes,
    *,
    window: int = 32,
    stride: int = 1,
) -> dict[str, Any]:
    """Jaccard similarity over sliding-window fingerprints (shift-tolerant)."""
    fa = set(window_fingerprints(a, window=window, stride=stride))
    fb = set(window_fingerprints(b, window=window, stride=stride))
    inter = fa & fb
    union = fa | fb
    score = (len(inter) / len(union)) if union else 1.0
    return {
        "method": "sliding_window_fingerprint_jaccard",
        "window": window,
        "stride": stride,
        "fingerprints_a": len(fa),
        "fingerprints_b": len(fb),
        "intersection": len(inter),
        "union": len(union),
        "jaccard": round(score, 6),
        "notes": (
            "Tolerant of small insertions/deletions that shift later bytes. "
            "Not a proof of shared semantic constructs."
        ),
    }


def sequence_match_blocks(
    a: bytes,
    b: bytes,
    *,
    max_blocks: int = 64,
) -> dict[str, Any]:
    """Optional difflib matching blocks for small files only."""
    size = max(len(a), len(b))
    if size > _SEQMATCH_MAX_BYTES:
        return {
            "method": "difflib.SequenceMatcher",
            "skipped": True,
            "reason": f"file too large for SequenceMatcher ({size} > {_SEQMATCH_MAX_BYTES})",
            "ratio": None,
            "blocks": [],
        }

    import difflib

    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    ratio = sm.ratio()
    blocks = []
    for block in sm.get_matching_blocks():
        if block.size == 0:
            continue
        blocks.append(
            {
                "a_start": block.a,
                "b_start": block.b,
                "length": block.size,
                "shift": block.b - block.a,
            }
        )
        if len(blocks) >= max_blocks:
            break
    return {
        "method": "difflib.SequenceMatcher",
        "skipped": False,
        "ratio": round(ratio, 6),
        "blocks": blocks,
        "blocks_truncated": len(sm.get_matching_blocks()) - 1 > max_blocks,
        "notes": (
            "Matching blocks can reveal shifted shared regions. "
            "Disabled automatically for large inputs."
        ),
    }


def robust_similarity(a: bytes, b: bytes) -> dict[str, Any]:
    """Combine aligned metrics with shift-tolerant fingerprints."""
    min_len = min(len(a), len(b))
    max_len = max(len(a), len(b))
    matching = sum(1 for i in range(min_len) if a[i] == b[i])
    aligned = (matching / max_len) if max_len else 1.0
    fp = fingerprint_jaccard(a, b)
    seq = sequence_match_blocks(a, b)
    return {
        "aligned_byte_similarity": round(aligned, 6),
        "matching_bytes_in_overlap": matching,
        "overlap_length": min_len,
        "size_a": len(a),
        "size_b": len(b),
        "fingerprint_jaccard": fp,
        "sequence_matcher": seq,
        "research_disclaimer": (
            "Similarity scores are descriptive only and do not identify MQL5 constructs."
        ),
    }
