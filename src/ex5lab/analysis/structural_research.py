"""Structural research stubs for EX5-like byte buffers .

Entropy / section heuristics only. No fake instruction decoder.
Region candidates always carry evidence notes stating uncertainty.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

# Empirically used elsewhere in ex5lab as a *heuristic* prefix window  -  not a
# verified executable/payload boundary.
DEFAULT_HEADER_HEURISTIC = 744
HIGH_ENTROPY_BITS = 7.0


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    n = len(data)
    counts = Counter(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def analyze_entropy_profile(
    data: bytes,
    *,
    header_heuristic: int = DEFAULT_HEADER_HEURISTIC,
    window: int = 64,
) -> dict[str, Any]:
    hdr_end = min(header_heuristic, len(data))
    header = data[:hdr_end]
    payload = data[hdr_end:]
    windows = []
    for i in range(0, len(data), window):
        chunk = data[i : i + window]
        windows.append(
            {
                "start": i,
                "end": i + len(chunk),
                "entropy": round(shannon_entropy(chunk), 6),
            }
        )
    return {
        "schema": "phase10_structural_entropy_v1",
        "size": len(data),
        "header_heuristic_end": hdr_end,
        "header_entropy": round(shannon_entropy(header), 6),
        "payload_entropy": round(shannon_entropy(payload), 6),
        "full_entropy": round(shannon_entropy(data), 6),
        "windows": windows,
        "evidence_note": (
            "Header/payload split uses a research heuristic window only. "
            "High entropy does not prove encryption or identify an ISA."
        ),
        "opcode_decoder": False,
    }


def region_candidates(
    data: bytes,
    *,
    header_heuristic: int = DEFAULT_HEADER_HEURISTIC,
    window: int = 64,
    high_entropy_bits: float = HIGH_ENTROPY_BITS,
) -> dict[str, Any]:
    """Propose opaque regions with evidence notes  -  not a section parser."""
    profile = analyze_entropy_profile(
        data, header_heuristic=header_heuristic, window=window
    )
    regions: list[dict[str, Any]] = []
    hdr_end = profile["header_heuristic_end"]
    if hdr_end > 0:
        regions.append(
            {
                "id": "header_heuristic",
                "start": 0,
                "end": hdr_end,
                "label": "possible_metadata_or_format_prefix",
                "entropy": profile["header_entropy"],
                "evidence_status": "HYPOTHETICAL",
                "evidence_note": (
                    f"Bytes [0,{hdr_end}) labeled by convention used in prior phases; "
                    "not a verified EX5 section table."
                ),
            }
        )
    if hdr_end < len(data):
        regions.append(
            {
                "id": "post_header_heuristic",
                "start": hdr_end,
                "end": len(data),
                "label": "opaque_remainder",
                "entropy": profile["payload_entropy"],
                "evidence_status": "UNKNOWN",
                "evidence_note": (
                    "Remainder after heuristic prefix. May mix code, data, padding. "
                    "No instruction boundaries claimed."
                ),
            }
        )

    high_ent = [
        w
        for w in profile["windows"]
        if w["entropy"] >= high_entropy_bits
    ]
    for w in high_ent[:16]:
        regions.append(
            {
                "id": f"high_entropy_{w['start']}_{w['end']}",
                "start": w["start"],
                "end": w["end"],
                "label": "high_entropy_window",
                "entropy": w["entropy"],
                "evidence_status": "HYPOTHETICAL",
                "evidence_note": (
                    "Elevated Shannon entropy window; could be compressed, encrypted, "
                    "or dense binary data. Not decoded."
                ),
            }
        )

    # Signature peek only if present  -  empirical ASCII 'EX5' from prior corpus.
    sig_note = None
    if len(data) >= 3 and data[:3] == b"EX5":
        sig_note = {
            "id": "ascii_ex5_prefix",
            "start": 0,
            "end": 3,
            "label": "empirical_signature_bytes",
            "evidence_status": "BEHAVIOR_INFERRED",
            "evidence_note": (
                "ASCII 'EX5' prefix observed in self-authored MetaEditor builds "
                "in earlier phases; still not an opcode map."
            ),
        }
        regions.insert(0, sig_note)

    return {
        "schema": "phase10_structural_regions_v1",
        "regions": regions,
        "entropy_profile_summary": {
            "header_entropy": profile["header_entropy"],
            "payload_entropy": profile["payload_entropy"],
            "full_entropy": profile["full_entropy"],
            "n_high_entropy_windows": len(high_ent),
        },
        "disclaimer": (
            "Structural heuristics only. No fake EX5 decoder. "
            "Do not treat region labels as recovered machine code."
        ),
    }


def analyze_file(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    data = Path(path).read_bytes()
    return {
        "path": str(path),
        "sha256": __import__("hashlib").sha256(data).hexdigest(),
        "entropy_profile": analyze_entropy_profile(data, **kwargs),
        "region_candidates": region_candidates(data, **kwargs),
    }
