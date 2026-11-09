"""High-level read-only file inspection."""

from __future__ import annotations

from typing import Any

from ex5lab.binary.entropy import byte_frequency, shannon_entropy
from ex5lab.binary.hashing import sha256_hex
from ex5lab.binary.strings import extract_printable_strings, extract_utf16le_strings
from ex5lab.binary.validation import (
    DEFAULT_MAX_BYTES,
    BinaryValidationError,
    looks_like_ex5_extension,
    validate_and_read,
)
from ex5lab.evidence import EvidenceClass, claim


def hex_preview(data: bytes, *, head: int = 64, tail: int = 32) -> dict[str, Any]:
    """Return hex/ASCII previews of file head and optional tail."""
    head_bytes = data[:head]
    tail_bytes = data[-tail:] if len(data) > head else b""

    def _row(chunk: bytes, base: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for i in range(0, len(chunk), 16):
            part = chunk[i : i + 16]
            ascii_repr = "".join(chr(b) if 32 <= b <= 126 else "." for b in part)
            rows.append(
                {
                    "offset": base + i,
                    "hex": part.hex(" "),
                    "ascii": ascii_repr,
                }
            )
        return rows

    preview: dict[str, Any] = {
        "head_bytes_requested": head,
        "tail_bytes_requested": tail,
        "head": _row(head_bytes, 0),
    }
    if tail_bytes and len(data) > head:
        preview["tail"] = _row(tail_bytes, len(data) - len(tail_bytes))
        preview["omitted_middle_bytes"] = max(0, len(data) - head - len(tail_bytes))
    else:
        preview["tail"] = []
        preview["omitted_middle_bytes"] = 0
    return preview


def magic_prefix_observation(data: bytes) -> dict[str, Any]:
    """Record leading bytes without asserting a verified EX5 header schema.

    Any similarity to known magic values is labeled as a hypothesis/heuristic.
    """
    prefix = data[:16]
    observations = [
        claim(
            "Leading bytes were recorded for later controlled comparison.",
            EvidenceClass.VERIFIED_OBSERVATION,
            evidence=f"prefix_hex={prefix.hex()}",
        )
    ]
    # Public community discussions sometimes mention EX5-looking prefixes;
    # we do NOT treat any specific pattern as confirmed without local evidence.
    if prefix.startswith(b"EX5"):
        observations.append(
            claim(
                "File begins with ASCII 'EX5'. This may indicate a tagged container, "
                "but the official EX5 on-disk schema is not publicly documented here.",
                EvidenceClass.PLAUSIBLE_HYPOTHESIS,
                evidence="prefix starts with 45 58 35 ('E','X','5')",
                notes="Requires corpus confirmation across compiler versions.",
            )
        )
    return {
        "prefix_hex": prefix.hex(" "),
        "prefix_ascii": "".join(chr(b) if 32 <= b <= 126 else "." for b in prefix),
        "claims": observations,
        "warning": (
            "Do not treat unverified offsets as established EX5 fields."
        ),
    }


def inspect_file(
    path: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    string_min_length: int = 4,
    hex_head: int = 64,
    hex_tail: int = 32,
    include_full_frequency: bool = False,
) -> dict[str, Any]:
    """Inspect a binary file and return a structured report.

    Raises BinaryValidationError for invalid inputs.
    """
    validated = validate_and_read(path, max_bytes=max_bytes)
    data = validated.data

    freq = byte_frequency(data)
    if not include_full_frequency:
        # Keep reports compact by default; full maps remain available on request.
        freq_summary = {
            "unique_bytes": freq["unique_bytes"],
            "most_common": freq["most_common"],
            "full_maps_omitted": True,
        }
    else:
        freq_summary = {**freq, "full_maps_omitted": False}

    report: dict[str, Any] = {
        "tool": "ex5lab.inspect",
        "phase": "0",
        "path": str(validated.path),
        "filename": validated.path.name,
        "extension_is_ex5": looks_like_ex5_extension(validated.path),
        "size_bytes": validated.size,
        "sha256": sha256_hex(data),
        "hex_preview": hex_preview(data, head=hex_head, tail=hex_tail),
        "byte_frequency": freq_summary,
        "shannon_entropy": shannon_entropy(data),
        "printable_strings": extract_printable_strings(
            data, min_length=string_min_length
        ),
        "utf16le_strings": extract_utf16le_strings(
            data, min_length=string_min_length
        ),
        "magic_prefix": magic_prefix_observation(data),
        "research_disclaimer": (
            "This report is a byte-level observation. It does not decode EX5 "
            "instructions, recover MQL5 source, or assert encryption/protection state."
        ),
    }
    return report


def inspect_file_safe(path: str, **kwargs: Any) -> dict[str, Any]:
    """Like inspect_file, but captures validation errors into the report."""
    try:
        return inspect_file(path, **kwargs)
    except BinaryValidationError as exc:
        return {
            "tool": "ex5lab.inspect",
            "phase": "0",
            "path": str(path),
            "error": {
                "type": "BinaryValidationError",
                "message": str(exc),
            },
            "ok": False,
        }
