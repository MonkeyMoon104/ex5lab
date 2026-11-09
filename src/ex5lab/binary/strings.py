"""Printable string extraction (heuristic)."""

from __future__ import annotations

import re
from typing import Any


def extract_printable_strings(
    data: bytes,
    *,
    min_length: int = 4,
    max_results: int = 500,
) -> dict[str, Any]:
    """Extract runs of printable ASCII characters.

    This is a generic binary heuristic. Matching strings do not prove that
    they are MQL5 identifiers, source fragments, or metadata fields.
    """
    if min_length < 1:
        raise ValueError("min_length must be >= 1")

    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % min_length)
    found: list[dict[str, Any]] = []
    for match in pattern.finditer(data):
        raw = match.group()
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            continue
        found.append(
            {
                "offset": match.start(),
                "length": len(raw),
                "encoding": "ascii",
                "value": text,
            }
        )
        if len(found) >= max_results:
            break

    return {
        "min_length": min_length,
        "max_results": max_results,
        "truncated": len(found) >= max_results,
        "count": len(found),
        "strings": found,
        "evidence_note": (
            "HEURISTIC  -  printable runs are not verified EX5 schema fields."
        ),
    }


def extract_utf16le_strings(
    data: bytes,
    *,
    min_length: int = 4,
    max_results: int = 500,
) -> dict[str, Any]:
    """Extract UTF-16LE runs of printable ASCII code units.

    Added after corpus observation that #property copyright/version
    text appeared as UTF-16LE near the file head on MetaEditor 5.0.0.6270
    unprotected builds. This remains a heuristic, not a schema claim.
    """
    if min_length < 1:
        raise ValueError("min_length must be >= 1")

    # (printable ASCII byte followed by 0x00), repeated min_length times.
    pattern = re.compile(rb"(?:[\x20-\x7e]\x00){%d,}" % min_length)
    found: list[dict[str, Any]] = []
    for match in pattern.finditer(data):
        raw = match.group()
        try:
            text = raw.decode("utf-16le")
        except UnicodeDecodeError:
            continue
        found.append(
            {
                "offset": match.start(),
                "length_bytes": len(raw),
                "length_chars": len(text),
                "encoding": "utf-16le",
                "value": text,
            }
        )
        if len(found) >= max_results:
            break

    return {
        "min_length": min_length,
        "max_results": max_results,
        "truncated": len(found) >= max_results,
        "count": len(found),
        "strings": found,
        "evidence_note": (
            "HEURISTIC  -  UTF-16LE printable runs observed in local unprotected "
            "corpus metadata; not an official field map."
        ),
    }
