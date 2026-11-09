"""Byte-frequency and Shannon entropy analysis."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any


def byte_frequency(data: bytes) -> dict[str, Any]:
    """Return absolute and relative frequencies for all observed byte values."""
    counts = Counter(data)
    length = len(data)
    # Sparse map keyed by hex byte for JSON friendliness
    absolute = {f"{b:02x}": counts[b] for b in sorted(counts)}
    relative = {
        f"{b:02x}": (counts[b] / length if length else 0.0) for b in sorted(counts)
    }
    return {
        "unique_bytes": len(counts),
        "absolute": absolute,
        "relative": relative,
        "most_common": [
            {"byte": f"{b:02x}", "count": c, "fraction": c / length if length else 0.0}
            for b, c in counts.most_common(16)
        ],
    }


def shannon_entropy(data: bytes) -> dict[str, Any]:
    """Shannon entropy in bits/byte over the empirical byte distribution.

    High entropy is consistent with compression, encryption, packed data,
    or simply well-distributed binary code. It does NOT prove encryption.
    """
    length = len(data)
    if length == 0:
        return {
            "bits_per_byte": 0.0,
            "max_bits_per_byte": 8.0,
            "normalized": 0.0,
            "interpretation": (
                "Empty input  -  entropy undefined; reported as 0.0 for convenience."
            ),
        }

    counts = Counter(data)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)

    normalized = entropy / 8.0
    if entropy < 3.0:
        interpretation = (
            "Low entropy  -  often structured/repeated data. "
            "Not a format identification."
        )
    elif entropy < 6.5:
        interpretation = (
            "Moderate entropy  -  common for mixed binary structures. "
            "Does not prove encryption or compression."
        )
    else:
        interpretation = (
            "High entropy  -  consistent with compression, encryption, packing, "
            "or dense machine code. DOES NOT PROVE ENCRYPTION."
        )

    return {
        "bits_per_byte": round(entropy, 6),
        "max_bits_per_byte": 8.0,
        "normalized": round(normalized, 6),
        "interpretation": interpretation,
        "evidence_note": (
            "HEURISTIC ONLY  -  entropy alone cannot establish EX5 protection, "
            "Cloud Protector status, or encoding scheme."
        ),
    }
