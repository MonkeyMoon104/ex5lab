"""Compilation and L4 certification provenance  -  fail closed, never invent evidence."""

from __future__ import annotations

from typing import Any


_COMPILE_REQUIRED = (
    "frozen_candidate_sha256",
    "compiler_version",
    "compiler_invocation_id",
    "compiled_at_utc",
)

_L4_REQUIRED = (
    "director_approved",
    "blind_protocol_id",
    "frozen_candidate_sha256",
    "approved_at_utc",
    "semantic_checks_ref",
)


def validate_compile_provenance(
    compile_info: dict[str, Any] | None,
    *,
    frozen_candidate_sha256: str,
) -> dict[str, Any]:
    """Accept L2 only with attributable fresh compile evidence for the frozen hash.

    A bare ``mq5_compiles=True`` flag is **not** sufficient.
    """
    info = dict(compile_info or {})
    if info.get("mq5_compiles") is not True:
        return {
            "ok": False,
            "mq5_compiles": None if info.get("mq5_compiles") is not True else False,
            "status": "UNVERIFIED",
            "reason": "no_successful_compile_recorded",
            "note": "L1 ≠ L2. Compilation remains unverified without attested MetaEditor evidence.",
        }

    missing = [k for k in _COMPILE_REQUIRED if not info.get(k)]
    if missing:
        return {
            "ok": False,
            "mq5_compiles": None,
            "status": "INCOMPLETE_PROVENANCE",
            "reason": "missing_fields:" + ",".join(missing),
            "rejected_bare_mq5_compiles_flag": True,
        }

    if info.get("frozen_candidate_sha256") != frozen_candidate_sha256:
        return {
            "ok": False,
            "mq5_compiles": None,
            "status": "PROVENANCE_HASH_MISMATCH",
            "reason": "compile_record_not_tied_to_frozen_candidate",
            "expected_frozen_sha256": frozen_candidate_sha256,
            "recorded_frozen_sha256": info.get("frozen_candidate_sha256"),
        }

    if info.get("director_compile_attested") is not True and info.get("provenance_attested") is not True:
        return {
            "ok": False,
            "mq5_compiles": None,
            "status": "UNATTESTED",
            "reason": "compile_success_not_director_attested",
            "rejected_bare_mq5_compiles_flag": True,
        }

    return {
        "ok": True,
        "mq5_compiles": True,
        "status": "VERIFIED",
        "compiler_version": info.get("compiler_version"),
        "compiler_invocation_id": info.get("compiler_invocation_id"),
        "compiled_at_utc": info.get("compiled_at_utc"),
        "frozen_candidate_sha256": frozen_candidate_sha256,
    }


def validate_l4_certification(
    certification: dict[str, Any] | None,
    *,
    frozen_candidate_sha256: str,
    synthetic_fixture: bool,
    structural_verification: str | None,
) -> dict[str, Any]:
    """L4 only via explicit reviewer certification  -  never from structural match alone.

    ``synthetic_fixture=False`` is a declaration, not proof of an independent blind trial.
    """
    if not certification:
        return {
            "l4_eligible": False,
            "status": "UNVERIFIED",
            "reason": "no_director_l4_certification",
            "note": (
                "L4 is not automatic. Provide a reviewer-approved certification record "
                "referencing the frozen candidate hash and blind protocol."
            ),
        }

    if synthetic_fixture:
        return {
            "l4_eligible": False,
            "status": "REJECTED_SYNTHETIC",
            "reason": "synthetic_fixture_cannot_receive_real_l4",
        }

    if structural_verification != "VERIFIED":
        return {
            "l4_eligible": False,
            "status": "REJECTED_STRUCTURE",
            "reason": "structural_not_verified",
        }

    missing = [k for k in _L4_REQUIRED if k not in certification or certification.get(k) in (None, "")]
    if missing:
        return {
            "l4_eligible": False,
            "status": "INCOMPLETE_CERTIFICATION",
            "reason": "missing_fields:" + ",".join(missing),
        }

    if certification.get("director_approved") is not True:
        return {
            "l4_eligible": False,
            "status": "NOT_APPROVED",
            "reason": "director_approved_not_true",
        }

    if certification.get("frozen_candidate_sha256") != frozen_candidate_sha256:
        return {
            "l4_eligible": False,
            "status": "CERT_HASH_MISMATCH",
            "reason": "certification_not_tied_to_frozen_candidate",
        }

    if certification.get("independent_blind_lab") is not True:
        return {
            "l4_eligible": False,
            "status": "UNVERIFIED",
            "reason": "independent_blind_lab_not_attested",
            "note": "Local freeze alone is not independent blind-lab evidence.",
        }

    return {
        "l4_eligible": True,
        "status": "CERTIFIED",
        "blind_protocol_id": certification.get("blind_protocol_id"),
        "approved_at_utc": certification.get("approved_at_utc"),
        "semantic_checks_ref": certification.get("semantic_checks_ref"),
        "limitations_ack": certification.get("limitations_ack"),
    }
