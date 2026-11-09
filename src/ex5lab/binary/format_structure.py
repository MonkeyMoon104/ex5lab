"""Evidence-backed EX5 structural field observations .

Does not invent opcodes or claim encryption without evidence.
"""

from __future__ import annotations

import re
from typing import Any

from ex5lab.binary.ex5_header import EMPIRICAL_KIND_BYTES, EX5_SIGNATURE, parse_ex5_prefix


def _utf16le_ascii_strings(data: bytes, *, min_chars: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    i = 0
    n = len(data)
    while i < n - 3:
        if data[i + 1] == 0 and 32 <= data[i] < 127:
            j = i
            chars: list[str] = []
            while j < n - 1 and data[j + 1] == 0 and 32 <= data[j] < 127:
                chars.append(chr(data[j]))
                j += 2
            if len(chars) >= min_chars:
                out.append(
                    {
                        "offset": i,
                        "length_bytes": j - i,
                        "text": "".join(chars),
                        "status": "EMPIRICAL_STRUCTURE",
                    }
                )
                i = j
                continue
        i += 1
    return out


def analyze_ex5_structure(data: bytes) -> dict[str, Any]:
    """Return provenance-tagged structural observations for one EX5 blob."""
    prefix = parse_ex5_prefix(data)
    fields: list[dict[str, Any]] = []

    if prefix.get("signature_ok"):
        fields.append(
            {
                "name": "signature",
                "offset": 0,
                "size": 3,
                "value": "EX5",
                "status": "VERIFIED_FORMAT_FIELD",
                "evidence": "ASCII EX5 across self-authored corpus",
            }
        )
    if prefix.get("kind_byte") is not None:
        fields.append(
            {
                "name": "empirical_kind_byte",
                "offset": 3,
                "size": 1,
                "value": prefix.get("kind_byte_hex"),
                "kind_class": prefix.get("kind_class"),
                "status": "EMPIRICAL_STRUCTURE",
                "evidence": "offset-3 correlates with program kind in controlled corpus",
            }
        )

    # Shared 32-byte prefix observation : bytes 0..31 often identical
    # within a same-day same-compiler script family  -  not an ISA map.
    fields.append(
        {
            "name": "common_prefix_window",
            "offset": 0,
            "size": 32,
            "hex": data[: min(32, len(data))].hex(),
            "status": "EMPIRICAL_STRUCTURE",
            "evidence": "identical across many same-compiler rebuilds; first diffs often at 32",
        }
    )

    # UTF-16-LE plaintext in early region (copyright / version)  -  metadata, not code.
    early = data[: min(len(data), 1200)]
    strings = _utf16le_ascii_strings(early)
    meta_hits = []
    for s in strings:
        role = "unclassified_utf16le"
        st = "EMPIRICAL_STRUCTURE"
        if re.fullmatch(r"\d+\.\d{2}", s["text"]):
            role = "version_like"
        elif "ex5lab" in s["text"] or "copyright" in s["text"].lower() or "Phase" in s["text"]:
            role = "copyright_or_identity_like"
        meta_hits.append({**s, "role": role, "status": st})

    # Heuristic 744-byte window remains provisional
    fields.append(
        {
            "name": "provisional_early_window",
            "offset": 0,
            "size": min(744, len(data)),
            "status": "UNRESOLVED",
            "evidence": "historical heuristic only  -  not a proven payload boundary",
        }
    )

    high_entropy_note = {
        "name": "remainder_after_early_window",
        "offset": min(744, len(data)),
        "size": max(0, len(data) - 744),
        "status": "UNRESOLVED",
        "evidence": (
            "Often near-max Shannon entropy in prior phases; not labeled encryption "
            "or machine code without a decode rule."
        ),
    }
    fields.append(high_entropy_note)

    return {
        "schema": "phase12_ex5_format_structure_v1",
        "size": len(data),
        "prefix_parse": prefix,
        "fields": fields,
        "early_utf16le_strings": meta_hits,
        "executable_isa_declared": False,
        "decoder_available": False,
    }
