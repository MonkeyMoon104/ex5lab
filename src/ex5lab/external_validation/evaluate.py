"""Stage 3 evaluation of a frozen candidate against unlocked ground truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ex5lab.external_validation.mql5_checks import (
    is_plausible_mql5_source,
    static_safety_review,
    syntax_shape_check,
)
from ex5lab.decoder.availability import DECODER_AVAILABLE, decoder_status
from ex5lab.experiment.compile_util import DEFAULT_METAEDITOR, sha256_file
from ex5lab.external_validation.freeze import verify_candidate_immutable
from ex5lab.external_validation.levels import achieved_levels
from ex5lab.external_validation.mechanisms import MechanismHypothesis
from ex5lab.external_validation.provenance import (
    validate_compile_provenance,
    validate_l4_certification,
)
from ex5lab.external_validation.structural import compare_profiles, extract_structural_profile
from ex5lab.external_validation.workflow import ChallengeStore, load_manifest
from ex5lab.policy.static_only import assert_static_reconstruction_context


def _try_compile_note(candidate_path: Path) -> dict[str, Any]:
    """Default: no automatic compile; L2 stays unverified."""
    me = DEFAULT_METAEDITOR
    available = me.is_file()
    return {
        "metaeditor_path": str(me),
        "metaeditor_available": available,
        "compile_attempted": False,
        "mq5_compiles": None,
        "status": "SKIPPED_NO_METAEDITOR" if not available else "AVAILABLE_BUT_NOT_AUTO_RUN",
        "note": (
            "Automatic compile of untrusted candidate MQ5 is not performed by default. "
            "L2 requires an attested compile record tied to the frozen candidate SHA-256."
        ),
        "candidate_path": str(candidate_path),
    }


def _public_profile(prof: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in prof.items() if k != "expression_asts_raw"}


def evaluate_frozen_challenge(
    store: ChallengeStore,
    *,
    record_compile: dict[str, Any] | None = None,
    converter_id: str | None = None,
    director_l4_certification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare frozen candidate to unlocked ground truth. Never sets DECODER_AVAILABLE.

    L4 is never automatic  -  pass ``director_l4_certification`` or store it on the
    challenge manifest under ``director_l4_certification``.
    """
    assert_static_reconstruction_context(uses_strategy_tester=False)

    man = load_manifest(store)
    immut = verify_candidate_immutable(store.dir)
    freeze = json.loads((store.dir / "candidate_freeze.json").read_text(encoding="utf-8"))
    cand_path = store.dir / "candidate_frozen.mq5"
    cand_text = cand_path.read_text(encoding="utf-8", errors="replace")
    frozen_sha = str(freeze.get("sha256") or "")

    if not store.unlock_path.is_file():
        return {
            "ok": False,
            "error": "ground_truth_not_unlocked",
            "note": "Call unlock_ground_truth after freeze before evaluate.",
            "ex5lab_decoder_available": DECODER_AVAILABLE,
        }
    if not store.ground_truth_path.is_file():
        return {
            "ok": False,
            "error": "missing_ground_truth",
            "ex5lab_decoder_available": DECODER_AVAILABLE,
        }

    gt_text = store.ground_truth_path.read_text(encoding="utf-8", errors="replace")
    gt_sha = sha256_file(store.ground_truth_path)

    plausible = is_plausible_mql5_source(cand_text)
    safety = static_safety_review(cand_text)
    shape = syntax_shape_check(cand_text)
    exp_prof = extract_structural_profile(gt_text)
    got_prof = extract_structural_profile(cand_text)
    structural = compare_profiles(exp_prof, got_prof)

    compile_raw = record_compile or _try_compile_note(cand_path)
    compile_prov = validate_compile_provenance(
        compile_raw, frozen_candidate_sha256=frozen_sha
    )
    compile_info = {**compile_raw, "provenance": compile_prov}

    synthetic = bool(man.get("synthetic_fixture"))
    l4_cert = director_l4_certification or man.get("director_l4_certification")
    l4_assessment = validate_l4_certification(
        l4_cert,
        frozen_candidate_sha256=frozen_sha,
        synthetic_fixture=synthetic,
        structural_verification=structural.get("structural_verification"),
    )

    negative_flags: list[str] = []
    if len(cand_text.strip()) < 40:
        negative_flags.append("too_short")
    if cand_text.count("TODO") >= 1 and not structural["structural_properties_match"]:
        negative_flags.append("todo_template_like")
    if structural.get("structural_verification") != "VERIFIED":
        negative_flags.append("structural_not_verified")

    # Never auto-set blind_semantic_evidence from structure / synthetic=False.
    flags = {
        "input_registered": True,
        "mq5_syntactically_valid": bool(
            plausible.get("ok") and shape.get("ok") and safety.get("ok")
        ),
        "mq5_compiles": compile_prov.get("mq5_compiles") if compile_prov.get("ok") else None,
        "compile_provenance_ok": bool(compile_prov.get("ok")),
        "structural_properties_match": bool(structural.get("structural_properties_match")),
        "structural_verification": structural.get("structural_verification"),
        "blind_semantic_evidence": False,  # deprecated auto-path; see director_l4_certified
        "director_l4_certified": bool(l4_assessment.get("l4_eligible")),
        "l4_status": l4_assessment.get("status"),
        "synthetic_fixture": synthetic,
        "binary_decoding_mechanism_verified": False,
    }
    levels = achieved_levels(flags)

    evidence_dimensions = {
        "L0_provenance": "REGISTERED" if flags["input_registered"] else "MISSING",
        "L1_syntax": "OK" if flags["mq5_syntactically_valid"] else "FAIL",
        "L2_compile": compile_prov.get("status", "UNVERIFIED"),
        "L3_structure_subset": structural.get("structural_verification"),
        "L4_blind": l4_assessment.get("status", "UNVERIFIED"),
        "L5_mechanism": "UNVERIFIED",
    }

    mechanism = {
        "cannot_distinguish_automatically": True,
        "possible_hypotheses": [m.value for m in MechanismHypothesis],
        "note": (
            "Structural subset match (L3) does not identify binary decoding vs retrieval "
            "vs reconstruction. L4 requires reviewer certification; L5 requires separate "
            "mechanism evidence."
        ),
        "preferred_label_without_l5": MechanismHypothesis.MECHANISM_UNKNOWN.value,
    }

    report = {
        "schema": "external_validation_evaluation_report_v3",
        "challenge_id": store.challenge_id,
        "synthetic_fixture": synthetic,
        "converter_id": converter_id or freeze.get("converter_id"),
        "ex5": man.get("ex5"),
        "candidate": {
            "sha256": freeze.get("sha256"),
            "size_bytes": freeze.get("size_bytes"),
            "immutability": immut,
        },
        "ground_truth": {"sha256": gt_sha, "size_bytes": store.ground_truth_path.stat().st_size},
        "static_checks": {
            "plausible_mql5": plausible,
            "static_safety": safety,
            "syntax_shape": shape,
        },
        "structural": structural,
        "expected_profile": _public_profile(exp_prof),
        "candidate_profile": _public_profile(got_prof),
        "compile": compile_info,
        "l4_assessment": l4_assessment,
        "evidence_dimensions": evidence_dimensions,
        "negative_control_flags": negative_flags,
        "validation_flags": flags,
        "achieved_levels": levels,
        "highest_level": levels[-1] if levels else None,
        "mechanism_assessment": mechanism,
        "ex5lab": {
            "decoder_available": DECODER_AVAILABLE,
            "decoder_status": decoder_status(),
            "note": (
                "External candidate results must NEVER be presented as ex5lab "
                "binary-decoder output."
            ),
        },
        "unverified_claims": [
            "binary_decoding_mechanism",
            "complete_expression_tree_isomorphism_beyond_subset",
            "cryptographically_independent_blind_lab",
            "full_mql5_semantic_equivalence",
            "automatic_l4_from_structure",
        ],
        "limitations": [
            "L3 is supported-subset structure only  -  not full semantic equivalence",
            "Unexpected entry handlers / reachable helpers prevent L3 VERIFIED",
            "Macros, includes, and conditional compilation force UNVERIFIED",
            "L1 syntactic plausibility is not L2 compilation",
            "Bare mq5_compiles=True is rejected without attested provenance",
            "L4 requires reviewer certification  -  synthetic=False is insufficient",
            "Local freeze alone is not independent blind-lab evidence",
            "L4 does not imply L5",
            "Ground-truth vault on the same host risks contamination if read early",
        ],
        "ok": flags["mq5_syntactically_valid"]
        and not (safety.get("status") == "REJECT_UNSAFE"),
    }
    return report
