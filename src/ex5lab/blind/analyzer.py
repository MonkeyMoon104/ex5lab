"""Blind analyzer for authorized EX5 inputs.

Hard rules:
- Reads only authorized EX5 paths (default: under input/ or explicit authorized_roots).
- Must not open oracle/ or any oracle/reference source tree.
- Must not invent MQ5 source; reconstruction fields stay explicit unknowns
  unless supported by extractable evidence (e.g. UTF-16LE metadata).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ex5lab.binary.hashing import sha256_hex
from ex5lab.binary.ex5_header import parse_ex5_prefix
from ex5lab.binary.inspect import inspect_file
from ex5lab.binary.sliding import sliding_window_stats
from ex5lab.binary.validation import BinaryValidationError, validate_and_read
from ex5lab.evidence import EvidenceClass, claim


class BlindAnalysisError(RuntimeError):
    pass


def _assert_not_oracle_path(path: Path) -> None:
    parts = {p.lower() for p in path.resolve().parts}
    if "oracle" in parts:
        raise BlindAnalysisError(f"Blind analyzer refused path under oracle/: {path}")


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _assert_authorized(path: Path, authorized_roots: Iterable[Path] | None, allow_non_input: bool) -> None:
    _assert_not_oracle_path(path)
    path = path.resolve()
    if allow_non_input:
        return
    roots = list(authorized_roots or [])
    if not roots:
        # default: require an 'input' path component OR explicit roots
        if "input" in {p.lower() for p in path.parts}:
            return
        raise BlindAnalysisError(
            f"Path not under authorized input roots and allow_non_input=False: {path}"
        )
    if any(_is_under(path, Path(r)) for r in roots):
        return
    raise BlindAnalysisError(
        f"Path not under authorized roots {roots}: {path}"
    )


def analyze_ex5_blind(
    ex5_path: str | Path,
    *,
    case_id: str = "blind_case",
    allow_non_input: bool = False,
    authorized_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Produce a frozen blind analysis report for one EX5 file."""
    path = Path(ex5_path)
    _assert_authorized(path, authorized_roots, allow_non_input)

    try:
        validated = validate_and_read(path)
    except BinaryValidationError as exc:
        raise BlindAnalysisError(str(exc)) from exc

    data = validated.data
    inspect = inspect_file(str(validated.path))
    sliding = sliding_window_stats(data, window=256, stride=128)

    prefix = data[:16]
    header_parse = parse_ex5_prefix(data)
    byte3 = header_parse.get("kind_byte")
    kind_class = header_parse.get("kind_class") or "unknown"
    kind_hypothesis = {
        "script": "script (corpus pattern)",
        "expert": "expert advisor (corpus pattern)",
        "indicator": "indicator (corpus pattern)",
        "service": "service (corpus pattern)",
        "unknown": "unknown",
    }.get(kind_class, "unknown")

    utf16 = inspect.get("utf16le_strings", {}).get("strings", [])
    reconstruction = {
        "mq5_source_emitted": False,
        "executable_logic_recovered": False,
        "reason": (
            "ex5lab analyzer does not fabricate MQ5. "
            "No ISA decode is available; only metadata/header observations are reported."
        ),
        "recoverable_fragments": {
            "utf16le_property_like_strings": [s["value"] for s in utf16],
            "ascii_printable_sample": [
                s["value"] for s in inspect.get("printable_strings", {}).get("strings", [])[:20]
            ],
        },
        "unknowns": [
            "instruction stream / bytecode layout",
            "full input parameter table",
            "strategy logic / control flow",
            "include dependency tree",
            "exact original source text",
        ],
    }

    claims = [
        claim(
            "File begins with ASCII EX5 magic.",
            EvidenceClass.VERIFIED_OBSERVATION if data[:3] == b"EX5" else EvidenceClass.UNKNOWN,
            evidence=f"prefix={prefix.hex(' ')}",
        ),
        claim(
            f"Offset-3 value is 0x{byte3:02x}; corpus-pattern kind guess: {kind_hypothesis}.",
            EvidenceClass.PLAUSIBLE_HYPOTHESIS,
            evidence="Compared only to prior self-authored corpus patterns; not a formal schema.",
        ),
        claim(
            "UTF-16LE near-header strings were extracted when present.",
            EvidenceClass.VERIFIED_OBSERVATION if utf16 else EvidenceClass.UNKNOWN,
            evidence=str([s["value"] for s in utf16]),
        ),
        claim(
            "Exact MQ5 reconstruction / executable logic recovery is not supported by current evidence.",
            EvidenceClass.VERIFIED_OBSERVATION,
            evidence="reconstruction.executable_logic_recovered=false",
        ),
    ]

    return {
        "schema_version": "3.0",
        "tool": "ex5lab.blind.analyzer",
        "phase": "3",
        "case_id": case_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "blind",
        "oracle_access": False,
        "path": str(validated.path),
        "size_bytes": validated.size,
        "sha256": sha256_hex(data),
        "header": {
            "prefix16_hex": prefix.hex(" "),
            "byte3": f"{byte3:02x}" if byte3 is not None else None,
            "kind_hypothesis": kind_hypothesis,
            "signature_ok": header_parse.get("signature_ok"),
            "kind_class": kind_class,
            "ex5_header_schema": header_parse.get("schema"),
            "starts_with_ex5": data[:3] == b"EX5",
        },
        "entropy": inspect.get("shannon_entropy"),
        "sliding_summary": sliding.get("summary"),
        "utf16le_strings": utf16,
        "printable_strings": inspect.get("printable_strings"),
        "ascii_string_count": inspect.get("printable_strings", {}).get("count"),
        "claims": claims,
        "reconstruction": reconstruction,
        "security": {
            "executed_binary": False,
            "cloud_protector_bypass_attempted": False,
            "oracle_tree_read": False,
            "isolation": "test-harness path authorization (not a hardened OS sandbox)",
        },
    }
