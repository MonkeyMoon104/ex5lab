"""EX5 signature vs empirical program-kind byte (evidence-based, not official ISA)."""

from __future__ import annotations

from typing import Any

# ASCII "EX5" magic observed on ordinary MetaEditor-produced EX5 files.
EX5_SIGNATURE = b"EX5"

# Empirically observed offset-3 values in self-authored MetaEditor builds.
# Hypotheses only - not an official MetaQuotes schema.
EMPIRICAL_KIND_BYTES: dict[int, str] = {
    0x01: "script",
    0x02: "expert",
    0x04: "indicator",
    0x05: "service",
}

HAS_CONSTRUCT = False
try:
    from construct import Byte, Bytes, Const, Struct  # type: ignore

    HAS_CONSTRUCT = True
except Exception:  # noqa: BLE001
    Struct = None  # type: ignore


def build_construct_schema():
    if not HAS_CONSTRUCT:
        return None
    return Struct(
        "signature" / Const(EX5_SIGNATURE),
        "kind_byte" / Byte,
        "opaque_after_kind" / Bytes(740),
    )


def parse_ex5_prefix(data: bytes, *, opaque_after: int = 741) -> dict[str, Any]:
    """Parse signature independently of kind byte.

    opaque_after counts bytes after the 3-byte signature (kind + following),
    default 741 => total 744-byte heuristic window used elsewhere.
    """
    out: dict[str, Any] = {
        "schema": "ex5_header_v2",
        "has_construct": HAS_CONSTRUCT,
        "executable_isa_declared": False,
        "note": (
            "Signature and kind_byte are empirically supported. "
            "Remaining fields are opaque. Not an opcode map."
        ),
    }
    if len(data) < 3:
        out["ok"] = False
        out["error"] = "too_short"
        return out
    if data[:3] != EX5_SIGNATURE:
        out["ok"] = False
        out["error"] = "signature_mismatch"
        out["observed_prefix"] = data[: min(4, len(data))].hex()
        return out

    out["ok"] = True
    out["signature"] = "EX5"
    out["signature_ok"] = True

    if len(data) < 4:
        out["kind_byte"] = None
        out["kind_class"] = "unknown"
        out["kind_known"] = False
        out["error"] = "truncated_after_signature"
        out["opaque_byte_count"] = 0
        return out

    kind = data[3]
    out["kind_byte"] = kind
    out["kind_byte_hex"] = f"{kind:02x}"
    if kind in EMPIRICAL_KIND_BYTES:
        out["kind_class"] = EMPIRICAL_KIND_BYTES[kind]
        out["kind_known"] = True
        out["kind_evidence"] = "empirical_corpus_hypothesis"
    else:
        out["kind_class"] = "unknown"
        out["kind_known"] = False
        out["kind_evidence"] = "unrecognized_kind_byte_not_rejected"

    # Do NOT reject unknown kind when signature is valid.
    rest = data[4:]
    out["opaque_byte_count"] = len(rest)
    out["opaque_after_signature_len"] = 1 + len(rest)  # kind + rest

    if HAS_CONSTRUCT and len(data) >= 744:
        schema = build_construct_schema()
        try:
            parsed = schema.parse(data[:744])
            out["construct_parse"] = {
                "signature_ok": bytes(parsed.signature) == EX5_SIGNATURE,
                "kind_byte": int(parsed.kind_byte),
                "opaque_after_kind_len": len(parsed.opaque_after_kind),
            }
        except Exception as exc:  # noqa: BLE001
            out["construct_parse_error"] = str(exc)
    return out


# Backward-compatible wrapper used by older call sites.
def parse_verified_prefix(data: bytes) -> dict[str, Any]:
    """Legacy name - now signature-correct (does not require kind==0x01)."""
    parsed = parse_ex5_prefix(data)
    # Map old error name for truncated-only cases; keep signature_mismatch distinct.
    if not parsed.get("ok") and parsed.get("error") == "signature_mismatch":
        parsed["error"] = "magic_mismatch"  # historical alias
    return parsed
