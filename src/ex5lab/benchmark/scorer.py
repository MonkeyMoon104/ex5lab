"""Dimensional oracle scoring  -  metadata success is not executable recovery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ex5lab.benchmark.integrity import IntegrityError, verify_freeze_bundle
from ex5lab.benchmark.oracle import load_source_oracle
from ex5lab.binary.hashing import sha256_hex


def _status(ok: bool | None) -> str:
    if ok is True:
        return "PASS"
    if ok is False:
        return "FAIL"
    return "UNKNOWN"


def score_case(
    *,
    freeze_manifest_path: Path,
    oracle_dir: Path,
    case_id: str | None = None,
    expected_ex5_path: Path | None = None,
    entry_mq5_name: str | None = None,
    build_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a frozen blind analysis against an independent source oracle.

    Dimensions are independent. A metadata PASS cannot inflate executable recovery.
    """
    try:
        integrity = verify_freeze_bundle(
            freeze_manifest_path=Path(freeze_manifest_path),
            expected_case_id=case_id,
            expected_ex5_path=expected_ex5_path,
        )
        process_integrity = {
            "status": "PASS",
            "detail": integrity,
        }
    except IntegrityError as exc:
        return {
            "schema_version": "3.0",
            "tool": "ex5lab.benchmark.scorer",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "dimensions": {
                "PROCESS_INTEGRITY": {"status": "FAIL", "detail": str(exc)},
                "METADATA_ACCURACY": {"status": "UNKNOWN", "detail": "skipped due to integrity failure"},
                "PROGRAM_KIND_HYPOTHESIS": {"status": "UNKNOWN", "detail": "skipped"},
                "EXECUTABLE_LOGIC_RECOVERY": {"status": "FAIL", "detail": "not evaluated; integrity failed"},
                "FUNCTIONAL_EQUIVALENCE": {"status": "FAIL", "detail": "not evaluated; integrity failed"},
            },
            "overall": {
                "executable_logic_recovered": False,
                "functional_equivalence_claimed": False,
                "source_oracle_status": "NOT_EVALUATED",
                "build_identity": "NOT_EVALUATED",
                "headline": "INTEGRITY_FAILURE",
                "warning": "Do not interpret this as decompilation accuracy.",
            },
            "error": str(exc),
        }

    freeze = json.loads(Path(freeze_manifest_path).read_text(encoding="utf-8"))
    blind_path = Path(integrity["blind_report_path"])
    blind = json.loads(blind_path.read_text(encoding="utf-8"))

    oracle = load_source_oracle(Path(oracle_dir), entry_name=entry_mq5_name)
    if oracle.get("status") == "ORACLE_MISSING":
        return {
            "schema_version": "3.0",
            "tool": "ex5lab.benchmark.scorer",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "dimensions": {
                "PROCESS_INTEGRITY": process_integrity,
                "METADATA_ACCURACY": {
                    "status": "ORACLE_MISSING",
                    "detail": oracle,
                    "note": "Cannot score metadata against source; EX5-derived manifest is not an oracle.",
                },
                "PROGRAM_KIND_HYPOTHESIS": {"status": "ORACLE_MISSING", "detail": "no source"},
                "EXECUTABLE_LOGIC_RECOVERY": {
                    "status": "FAIL",
                    "executable_logic_recovered": False,
                    "detail": "No MQ5 reconstruction was verified; oracle missing.",
                },
                "FUNCTIONAL_EQUIVALENCE": {
                    "status": "FAIL",
                    "detail": "Cannot claim equivalence without oracle and behavioral tests.",
                },
            },
            "overall": {
                "executable_logic_recovered": False,
                "functional_equivalence_claimed": False,
                "source_oracle_status": "ORACLE_MISSING",
                "build_identity": "BUILD_IDENTITY_UNVERIFIED",
                "headline": "ORACLE_MISSING",
                "warning": "An EX5-derived manifest alone is not a valid source oracle.",
            },
        }

    # METADATA from actual source properties
    props = oracle["properties"]
    utf16_vals = [s.get("value") for s in blind.get("utf16le_strings", [])]
    ascii_vals = [
        s.get("value")
        for s in (blind.get("printable_strings") or {}).get("strings", [])
    ] if isinstance(blind.get("printable_strings"), dict) else []
    # also accept recovery fragment lists
    frags = (
        (blind.get("reconstruction") or {})
        .get("recoverable_fragments", {})
        .get("utf16le_property_like_strings", [])
    )
    hay = set(utf16_vals) | set(frags)

    meta_checks = {}
    for key in ("copyright", "version"):
        expected = props.get(key)
        if expected is None:
            meta_checks[key] = {"status": "UNKNOWN", "expected": None, "reason": "property absent in source"}
        else:
            ok = expected in hay
            meta_checks[key] = {
                "status": _status(ok),
                "expected": expected,
                "observed_in_blind": expected if ok else None,
            }
    desc = props.get("description")
    if desc:
        # description may not appear as UTF-16LE near header; UNKNOWN if not found (not FAIL)
        found = desc in hay or any(desc in (v or "") for v in hay)
        meta_checks["description"] = {
            "status": "PASS" if found else "UNKNOWN",
            "expected": desc,
            "note": "Description often absent from near-header UTF-16LE extracts.",
        }

    meta_statuses = [c["status"] for c in meta_checks.values()]
    if any(s == "FAIL" for s in meta_statuses):
        meta_overall = "FAIL"
    elif any(s == "PASS" for s in meta_statuses) and all(s in {"PASS", "UNKNOWN"} for s in meta_statuses):
        meta_overall = "PASS" if all(s == "PASS" for s in meta_statuses if s != "UNKNOWN") or any(s == "PASS" for s in meta_statuses) else "UNKNOWN"
        # If copyright+version PASS, call METADATA_ACCURACY PASS even if description UNKNOWN
        if meta_checks.get("copyright", {}).get("status") == "PASS" and meta_checks.get("version", {}).get("status") == "PASS":
            meta_overall = "PASS"
    else:
        meta_overall = "UNKNOWN"

    # PROGRAM KIND
    expected_kind = oracle["program_kind"]
    hyp = (blind.get("header") or {}).get("kind_hypothesis", "")
    byte3 = (blind.get("header") or {}).get("byte3")
    kind_map = {"01": "script", "02": "expert", "04": "indicator", "05": "service"}
    kind_from_byte = kind_map.get(byte3 or "", "unknown")
    kind_ok = False
    if expected_kind == "expert":
        kind_ok = "expert" in hyp.lower() or kind_from_byte == "expert"
    elif expected_kind == "script":
        kind_ok = "script" in hyp.lower() or kind_from_byte == "script"
    elif expected_kind == "indicator":
        kind_ok = "indicator" in hyp.lower() or kind_from_byte == "indicator"
    elif expected_kind == "service":
        kind_ok = "service" in hyp.lower() or kind_from_byte == "service"

    # EXECUTABLE LOGIC ? only true if reconstruction emitted AND verified (never here yet)
    recon = blind.get("reconstruction") or {}
    emitted = bool(recon.get("mq5_source_emitted"))
    exec_recovered = False
    exec_detail = (
        "executable_logic_recovered=false; does not decode payload ISA / control flow."
    )
    if emitted:
        exec_detail = (
            "Blind report claims mq5_source_emitted=true but no verified logic recovery pipeline exists; FAIL."
        )
        exec_status = "FAIL"
    else:
        exec_status = "FAIL"  # honest: not recovered
        # Using FAIL for "not recovered" is correct for EXECUTABLE_LOGIC_RECOVERY dimension

    # FUNCTIONAL EQUIVALENCE ? requires behavioral evidence; absent => FAIL/not claimed
    fe_status = "FAIL"
    fe_detail = "No behavioral equivalence tests executed; claim forbidden."

    # Build identity
    prov = build_provenance or {}
    if prov.get("exact_match_verified"):
        build_identity = "BUILD_IDENTITY_VERIFIED"
    else:
        build_identity = "BUILD_IDENTITY_UNVERIFIED"

    dims = {
        "PROCESS_INTEGRITY": process_integrity,
        "METADATA_ACCURACY": {
            "status": meta_overall,
            "checks": meta_checks,
            "oracle_source": oracle["entry_path"],
            "note": "Expected values parsed from MQ5 #property, not metadata_observed_in_ex5.",
        },
        "PROGRAM_KIND_HYPOTHESIS": {
            "status": _status(kind_ok),
            "expected_kind": expected_kind,
            "blind_hypothesis": hyp,
            "byte3": byte3,
            "byte3_mapped": kind_from_byte,
            "evidence_class": "plausible_hypothesis",
        },
        "EXECUTABLE_LOGIC_RECOVERY": {
            "status": exec_status,
            "executable_logic_recovered": exec_recovered,
            "mq5_source_emitted": emitted,
            "detail": exec_detail,
        },
        "FUNCTIONAL_EQUIVALENCE": {
            "status": fe_status,
            "functional_equivalence_claimed": False,
            "detail": fe_detail,
        },
    }

    headline = "METADATA_ONLY"
    if meta_overall == "PASS" and exec_recovered:
        headline = "LOGIC_RECOVERED"  # unreachable currently
    elif meta_overall == "FAIL":
        headline = "METADATA_MISMATCH"
    elif oracle.get("internal_include_closure_complete") is False:
        headline = "METADATA_PARTIAL_ORACLE_INCOMPLETE_INCLUDES"

    return {
        "schema_version": "3.0",
        "tool": "ex5lab.benchmark.scorer",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "case_id": integrity.get("case_id"),
        "dimensions": dims,
        "oracle": {
            "status": oracle["status"],
            "entry": oracle.get("entry_path"),
            "program_kind": expected_kind,
            "internal_include_closure_complete": oracle.get("internal_include_closure_complete"),
            "project_includes_missing": oracle.get("project_includes_missing"),
            "stdlib_or_external_missing": oracle.get("stdlib_or_external_missing"),
            "internal_include_count": oracle.get("internal_include_count"),
        },
        "build_identity": build_identity,
        "build_provenance": prov or {
            "compiler_version": None,
            "optimize": None,
            "architecture": None,
            "note": "Original build provenance unavailable.",
        },
        "overall": {
            "executable_logic_recovered": False,
            "functional_equivalence_claimed": False,
            "source_oracle_status": oracle["status"],
            "build_identity": build_identity,
            "headline": headline,
            "warning": (
                "Dimensional scores are independent. METADATA_ACCURACY PASS is not "
                "decompilation accuracy and must not be summarized as N/N source recovery."
            ),
        },
    }


def score_blind_against_oracle(
    blind_report_path: str | Path,
    *,
    oracle_dir: str | Path,
    case_manifest_path: str | Path | None = None,
    freeze_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    blind_report_path = Path(blind_report_path)
    if freeze_manifest_path is None:
        # Prefer sibling freeze_manifest.json
        sib = blind_report_path.parent / "freeze_manifest.json"
        freeze_manifest_path = sib if sib.is_file() else None
    if freeze_manifest_path is None or not Path(freeze_manifest_path).is_file():
        return {
            "schema_version": "3.0",
            "error": "freeze_manifest.json required for scoring (integrity remediation)",
            "overall": {
                "headline": "INTEGRITY_FAILURE",
                "executable_logic_recovered": False,
                "functional_equivalence_claimed": False,
                "source_oracle_status": "NOT_EVALUATED",
            },
        }
    return score_case(
        freeze_manifest_path=Path(freeze_manifest_path),
        oracle_dir=Path(oracle_dir),
        expected_ex5_path=None,
    )
