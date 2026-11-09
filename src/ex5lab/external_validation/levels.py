"""Validation ladder L0-L5 for external converter candidates.

Levels are independent evidence dimensions, not an automatic progressive score.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ValidationLevel(str, Enum):
    L0_INPUT_REGISTERED = "L0_INPUT_REGISTERED"
    L1_MQ5_SYNTACTICALLY_VALID = "L1_MQ5_SYNTACTICALLY_VALID"
    L2_MQ5_COMPILES = "L2_MQ5_COMPILES"
    L3_STRUCTURAL_PROPERTIES_MATCH = "L3_STRUCTURAL_PROPERTIES_MATCH"
    L4_BLIND_SEMANTIC_EVIDENCE = "L4_BLIND_SEMANTIC_EVIDENCE"
    L5_BINARY_DECODING_MECHANISM_VERIFIED = "L5_BINARY_DECODING_MECHANISM_VERIFIED"


LEVEL_ORDER = [
    ValidationLevel.L0_INPUT_REGISTERED,
    ValidationLevel.L1_MQ5_SYNTACTICALLY_VALID,
    ValidationLevel.L2_MQ5_COMPILES,
    ValidationLevel.L3_STRUCTURAL_PROPERTIES_MATCH,
    ValidationLevel.L4_BLIND_SEMANTIC_EVIDENCE,
    ValidationLevel.L5_BINARY_DECODING_MECHANISM_VERIFIED,
]


def achieved_levels(flags: dict[str, Any]) -> list[str]:
    """Return achieved levels from evidence flags. Never invent L4/L5.

    L2 requires compile_provenance_ok (not a bare mq5_compiles flag).
    L3 requires structural_verification == VERIFIED (subset only).
    L4 requires director_l4_certified  -  never structural match or synthetic=False alone.
    """
    out: list[str] = []
    if flags.get("input_registered"):
        out.append(ValidationLevel.L0_INPUT_REGISTERED.value)
    if flags.get("mq5_syntactically_valid"):
        out.append(ValidationLevel.L1_MQ5_SYNTACTICALLY_VALID.value)

    if flags.get("mq5_compiles") is True and flags.get("compile_provenance_ok") is True:
        out.append(ValidationLevel.L2_MQ5_COMPILES.value)

    structural_ok = flags.get("structural_properties_match") is True
    structural_verified = flags.get("structural_verification") == "VERIFIED"
    if structural_ok and structural_verified:
        out.append(ValidationLevel.L3_STRUCTURAL_PROPERTIES_MATCH.value)

    if (
        flags.get("director_l4_certified") is True
        and flags.get("l4_status") == "CERTIFIED"
        and flags.get("synthetic_fixture") is not True
    ):
        out.append(ValidationLevel.L4_BLIND_SEMANTIC_EVIDENCE.value)

    if flags.get("binary_decoding_mechanism_verified") is True:
        out.append(ValidationLevel.L5_BINARY_DECODING_MECHANISM_VERIFIED.value)
    return out


def level_notes() -> dict[str, str]:
    return {
        ValidationLevel.L0_INPUT_REGISTERED.value: "EX5 (+ optional provenance) registered with hashes.",
        ValidationLevel.L1_MQ5_SYNTACTICALLY_VALID.value: "Syntactic plausibility only  -  not compilation.",
        ValidationLevel.L2_MQ5_COMPILES.value: (
            "Fresh attested MetaEditor compile for the exact frozen MQ5 hash "
            "(compiler version + invocation provenance required)."
        ),
        ValidationLevel.L3_STRUCTURAL_PROPERTIES_MATCH.value: (
            "Supported-subset executable structure verified (entry sets, reachable bodies, "
            "narrow expression ASTs). NOT full semantic equivalence."
        ),
        ValidationLevel.L4_BLIND_SEMANTIC_EVIDENCE.value: (
            "reviewer-certified independent blind evaluation evidence only  -  "
            "never auto-awarded from structural match or synthetic=False metadata."
        ),
        ValidationLevel.L5_BINARY_DECODING_MECHANISM_VERIFIED.value: (
            "Independent evidence of binary-derived executable decoding  -  NOT implied by L4."
        ),
    }
