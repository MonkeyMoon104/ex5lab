"""Replay/audit historical evidence without MetaEditor."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ex5lab.analysis.sequence_runner import (
    DEFAULT_RANDOM_SEED,
    run_sequence_study,
    summarize_arm_means,
)
from ex5lab.experiment.build_schema import (
    IncompleteBuildRecordError,
    infer_build_index_from_artifact,
    validate_build_records,
)
from ex5lab.experiment.evidence_paths import (
    project_root_from,
    resolve_evidence_path,
    sha256_file,
    verify_artifact_sha,
)
from ex5lab.experiment.path_portability import (
    UnsafeEvidencePathError,
    extract_repo_relative_evidence_path,
)


EXPECTED_PHASE5_BUILDS = 108

# Scientific / integrity audit vocabulary . NOT_REPRODUCIBLE is reserved
# for statistical mismatch after a complete replay  -  never for missing deps or budgets.
AUDIT_STATUSES = frozenset(
    {
        "VERIFIED",
        "PARTIALLY_VERIFIED",
        "NOT_REPRODUCIBLE",
        "MISSING_EVIDENCE",
        "DEPENDENCY_UNAVAILABLE",
        "RESOURCE_LIMIT",
        "INVALID_EXPERIMENT",
    }
)

MODE_INTEGRITY_ONLY = "integrity_only"
MODE_FULL = "full"
AUDIT_MODES = frozenset({MODE_INTEGRITY_ONLY, MODE_FULL})

RESEARCH_OPTIONAL_DEPS = ("pydivsufsort", "numpy")


def check_research_dependencies() -> dict[str, Any]:
    """Probe optional research deps required for full scientific LCS replay."""
    missing: list[str] = []
    present: list[str] = []
    for name in RESEARCH_OPTIONAL_DEPS:
        try:
            __import__(name)
            present.append(name)
        except ImportError:
            missing.append(name)
    return {
        "ok": len(missing) == 0,
        "present": present,
        "missing": missing,
        "required_for_full_replay": list(RESEARCH_OPTIONAL_DEPS),
    }


def preview_migrate_phase5_build_table(
    *,
    root: Path | None = None,
    compiler_version: str = "5.0.0.6270",
) -> dict[str, Any]:
    """Read-only migration preview. Never writes canonical files."""
    root = root or project_root_from()
    legacy_path = root / "reports" / "phase5" / "build_table.json"
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    builds_out: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for raw in legacy.get("builds", []):
        abs_ex5 = raw.get("evidence_ex5")
        try:
            eid = raw.get("experiment_id")
            rel = extract_repo_relative_evidence_path(abs_ex5 or "", experiment_id=eid)
            if not rel:
                # try artifact already relative
                cand = str(raw.get("artifact_relpath") or "")
                rel = extract_repo_relative_evidence_path(cand, experiment_id=eid) if cand else None
            if not rel:
                bi = infer_build_index_from_artifact(abs_ex5 or "")
                errors.append(
                    {
                        "error": "cannot_map_portable_path",
                        "record": abs_ex5,
                        "inferred_build_index": bi,
                    }
                )
                continue
            bi = infer_build_index_from_artifact(rel)
            if bi is None:
                errors.append({"error": "missing_build_index", "artifact": rel})
                continue
            path = resolve_evidence_path(rel, root=root, abs_hint=None)
            live_sha = sha256_file(path)
            expected = (raw.get("ex5_sha256") or "").lower()
            if expected and live_sha != expected:
                errors.append(
                    {
                        "error": "sha_mismatch",
                        "artifact": rel,
                        "expected": expected,
                        "live": live_sha,
                    }
                )
                continue
            rec = {
                "build_index": bi,
                "source_group_id": raw.get("group_id") or raw.get("experiment_id"),
                "source_sha256": raw.get("source_sha256"),
                "ex5_sha256": expected or live_sha,
                "experiment_id": raw.get("experiment_id"),
                "split": raw.get("split"),
                "label": raw.get("label"),
                "artifact_relpath": rel.replace(chr(92), "/"),
                "compiler_version": compiler_version,
                "family": raw.get("family"),
                "template_family": raw.get("family"),
                "optimize_setting": raw.get("optimize_setting"),
                "staging_mq5": raw.get("staging_mq5"),
                "evidence_ex5": abs_ex5,
                "ex5_size": raw.get("ex5_size"),
                "compile_status": raw.get("compile_status"),
                "migration_note": (
                    "build_index from rN.ex5 basename via PureWindowsPath/PurePosixPath; "
                    "portable artifact_relpath under reports/phase5/ex5/"
                ),
            }
            validate_build_records([rec], project_root=root)
            builds_out.append(rec)
        except (UnsafeEvidencePathError, FileNotFoundError, IncompleteBuildRecordError) as exc:
            errors.append({"error": str(exc), "evidence_ex5": abs_ex5})
        except Exception as exc:  # noqa: BLE001
            errors.append({"error": f"unexpected:{exc}", "evidence_ex5": abs_ex5})

    n_legacy = len(legacy.get("builds", []))
    complete = len(errors) == 0 and len(builds_out) == n_legacy and n_legacy == EXPECTED_PHASE5_BUILDS
    return {
        "schema": "build_table_canonical_v1",
        "phase": 5,
        "migrated_from": "reports/phase5/build_table.json",
        "n_legacy": n_legacy,
        "n_canonical": len(builds_out),
        "n_errors": len(errors),
        "errors": errors,
        "complete": complete,
        "fixed_staging": legacy.get("fixed_staging"),
        "builds": builds_out,
        "note": (
            "Preview only unless migrate_phase5_build_table(apply=True) replaces canonical "
            "transactionally after validation."
        ),
    }


def _atomic_replace_json(dest: Path, payload: dict[str, Any]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        check = json.loads(tmp_path.read_text(encoding="utf-8"))
        if check.get("n_canonical", -1) != len(check.get("builds", [])):
            raise RuntimeError("canonical temp failed consistency check")
        os.replace(tmp_path, dest)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def migrate_phase5_build_table(
    *,
    root: Path | None = None,
    compiler_version: str = "5.0.0.6270",
    apply: bool = False,
    require_complete: bool = True,
    expected_builds: int = EXPECTED_PHASE5_BUILDS,
) -> dict[str, Any]:
    """Transactional migration. Default apply=False is inspect-only (no overwrite).

    When apply=True, replaces build_table_canonical.json only if preview is complete
    (or require_complete=False and n_canonical > 0  -  still refuses empty overwrite).
    """
    root = root or project_root_from()
    dest = root / "reports" / "phase5" / "build_table_canonical.json"
    previous_exists = dest.is_file()
    previous_count = None
    if previous_exists:
        try:
            previous_count = len(json.loads(dest.read_text(encoding="utf-8")).get("builds", []))
        except Exception:  # noqa: BLE001
            previous_count = None

    preview = preview_migrate_phase5_build_table(root=root, compiler_version=compiler_version)
    preview["previous_canonical_exists"] = previous_exists
    preview["previous_canonical_count"] = previous_count
    preview["applied"] = False
    preview["preserved_previous"] = True

    if not apply:
        preview["note"] = "Inspect-only preview; canonical file not modified."
        return preview

    # Apply-time revalidation: re-run preview immediately before write (anti-TOCTOU).
    fresh = preview_migrate_phase5_build_table(root=root, compiler_version=compiler_version)
    fresh["previous_canonical_exists"] = previous_exists
    fresh["previous_canonical_count"] = previous_count
    fresh["applied"] = False
    fresh["preserved_previous"] = True
    fresh["apply_revalidated"] = True

    refuse = False
    reason = None
    if require_complete and not fresh.get("complete"):
        refuse = True
        reason = "incomplete_migration"
    if fresh["n_canonical"] == 0:
        refuse = True
        reason = "empty_canonical_refused"
    if require_complete and fresh["n_canonical"] != expected_builds:
        refuse = True
        reason = f"expected_{expected_builds}_got_{fresh['n_canonical']}"
    if not require_complete:
        fresh["warning"] = (
            "require_complete=False allows partial canonical overwrite; "
            "not recommended for research replay."
        )

    if refuse:
        fresh["applied"] = False
        fresh["preserved_previous"] = True
        fresh["refusal_reason"] = reason
        fresh["note"] = (
            "Migration refused after apply-time revalidation; "
            "existing build_table_canonical.json left unchanged."
        )
        return fresh

    out = {
        **fresh,
        "note": (
            "Authoritative canonical table after transactional migration "
            "with apply-time SHA revalidation."
        ),
    }
    out.pop("refusal_reason", None)
    _atomic_replace_json(dest, out)
    out["applied"] = True
    out["preserved_previous"] = False
    out["canonical_path"] = "reports/phase5/build_table_canonical.json"
    return out


def load_canonical_builds(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or project_root_from()
    path = root / "reports" / "phase5" / "build_table_canonical.json"
    if not path.is_file():
        raise FileNotFoundError("build_table_canonical.json missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    builds = data.get("builds") or []
    if len(builds) < EXPECTED_PHASE5_BUILDS:
        raise IncompleteBuildRecordError(
            f"canonical table incomplete: {len(builds)} < {EXPECTED_PHASE5_BUILDS}"
        )
    return builds


_ARM_NAMES = (
    "same_source_rebuilds",
    "holdout_present_r1",
    "holdout_absent_r1",
    "cross_class_r1",
    "randomized_control",
)


def _recomputed_block_status(recomputed: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map arm-level completeness / pair statuses to audit blocking statuses.

    RESOURCE_LIMIT and DEPENDENCY_UNAVAILABLE must not become NOT_REPRODUCIBLE.
    """
    if recomputed is None:
        return {
            "status": "MISSING_EVIDENCE",
            "reason": "recomputed_arm_null",
        }
    completeness = recomputed.get("completeness")
    if completeness == "DEPENDENCY_UNAVAILABLE":
        return {
            "status": "DEPENDENCY_UNAVAILABLE",
            "reason": "arm_completeness_dependency_unavailable",
            "completeness": completeness,
        }
    if completeness == "RESOURCE_LIMIT":
        return {
            "status": "RESOURCE_LIMIT",
            "reason": "arm_completeness_resource_limit",
            "completeness": completeness,
        }
    pairs = (recomputed.get("lcs") or {}).get("pairs") or []
    if any(p.get("status") == "DEPENDENCY_UNAVAILABLE" for p in pairs):
        return {
            "status": "DEPENDENCY_UNAVAILABLE",
            "reason": "pair_dependency_unavailable",
            "completeness": completeness,
        }
    if any(p.get("status") == "RESOURCE_LIMIT" for p in pairs):
        return {
            "status": "RESOURCE_LIMIT",
            "reason": "pair_resource_limit",
            "completeness": completeness,
        }
    return None


def compare_arm_means(
    published: dict[str, Any] | None,
    recomputed: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare published vs recomputed arm means with status taxonomy.

    NOT_REPRODUCIBLE only when both sides produced LCS means that disagree.
    """
    if published is None and recomputed is None:
        return {"status": "BOTH_NULL"}

    block = _recomputed_block_status(recomputed)
    if block is not None and block["status"] != "MISSING_EVIDENCE":
        return block

    if published is None or recomputed is None:
        # One side absent is missing evidence / incomplete experiment  -  not a
        # statistical mismatch claim.
        return {
            "status": "MISSING_EVIDENCE",
            "reason": "one_side_null",
            "published_present": published is not None,
            "recomputed_present": recomputed is not None,
        }

    pub_lcs = (published.get("lcs") or {}).get("mean_length")
    re_lcs = (recomputed.get("lcs") or {}).get("mean_length")
    if pub_lcs is None and re_lcs is None:
        return {
            "status": "MISSING_EVIDENCE",
            "reason": "both_lcs_means_null",
            "completeness": recomputed.get("completeness"),
        }
    if pub_lcs is None or re_lcs is None:
        # Prefer blocking statuses already handled; remaining null mean after a
        # "complete" arm is treated as missing evidence, not mismatch.
        return {
            "status": "MISSING_EVIDENCE",
            "reason": "missing_lcs_mean",
            "published_lcs_mean": pub_lcs,
            "recomputed_lcs_mean": re_lcs,
            "completeness": recomputed.get("completeness"),
        }
    ok = abs(float(pub_lcs) - float(re_lcs)) <= 0.51
    return {
        "status": "VERIFIED" if ok else "NOT_REPRODUCIBLE",
        "published_lcs_mean": pub_lcs,
        "recomputed_lcs_mean": re_lcs,
        "delta": float(re_lcs) - float(pub_lcs),
        "completeness": recomputed.get("completeness"),
    }


# Back-compat alias used by older call sites / tests
_compare_means = compare_arm_means


def _integrity_status(sha_ok_n: int, expected: int = EXPECTED_PHASE5_BUILDS) -> str:
    if sha_ok_n <= 0:
        return "MISSING_EVIDENCE"
    if sha_ok_n == expected:
        return "VERIFIED"
    return "PARTIALLY_VERIFIED"


def _aggregate_scientific_status(statuses: list[str]) -> str:
    """Roll up arm comparison statuses for full scientific replay."""
    if not statuses:
        return "MISSING_EVIDENCE"
    # Blocking infrastructure statuses dominate mismatch labeling
    if any(s == "DEPENDENCY_UNAVAILABLE" for s in statuses):
        return "DEPENDENCY_UNAVAILABLE"
    if any(s == "RESOURCE_LIMIT" for s in statuses):
        return "RESOURCE_LIMIT"
    if any(s == "INVALID_EXPERIMENT" for s in statuses):
        return "INVALID_EXPERIMENT"
    if any(s == "MISSING_EVIDENCE" for s in statuses):
        if all(s == "MISSING_EVIDENCE" for s in statuses):
            return "MISSING_EVIDENCE"
        return "PARTIALLY_VERIFIED"
    if any(s == "NOT_REPRODUCIBLE" for s in statuses):
        # Some arms mismatch while others may verify -> partial scientific claim
        if all(s == "NOT_REPRODUCIBLE" for s in statuses):
            return "NOT_REPRODUCIBLE"
        return "PARTIALLY_VERIFIED"
    if all(s == "VERIFIED" for s in statuses):
        return "VERIFIED"
    if any(s == "PARTIALLY_VERIFIED" for s in statuses):
        return "PARTIALLY_VERIFIED"
    return "PARTIALLY_VERIFIED"


def _combine_overall(
    *,
    mode: str,
    integrity_status: str,
    scientific_status: str | None,
) -> str:
    if mode == MODE_INTEGRITY_ONLY:
        return integrity_status
    if integrity_status == "MISSING_EVIDENCE":
        return "MISSING_EVIDENCE"
    if scientific_status is None:
        return integrity_status
    if scientific_status in {
        "DEPENDENCY_UNAVAILABLE",
        "RESOURCE_LIMIT",
        "INVALID_EXPERIMENT",
        "MISSING_EVIDENCE",
        "NOT_REPRODUCIBLE",
    }:
        return scientific_status
    if integrity_status != "VERIFIED":
        return "PARTIALLY_VERIFIED"
    return scientific_status


def audit_phase5_evidence(
    *,
    root: Path | None = None,
    random_seed: int = DEFAULT_RANDOM_SEED,
    apply_migration: bool = False,
    mode: str = MODE_FULL,
) -> dict[str, Any]:
    """Replay/verify evidence. Does not destroy canonical tables on preview failure.

    Modes:
      integrity_only  -  hash/path verify only; never claims statistical arm VERIFIED
      full  -  requires research deps for scientific LCS replay; labels dep/budget gaps
             distinctly from NOT_REPRODUCIBLE mismatch
    """
    if mode not in AUDIT_MODES:
        raise ValueError(f"unsupported audit mode {mode!r}; expected one of {sorted(AUDIT_MODES)}")

    root = root or project_root_from()
    deps = check_research_dependencies()
    preview = preview_migrate_phase5_build_table(root=root)
    migration_meta = {
        "preview_n_canonical": preview["n_canonical"],
        "preview_n_errors": preview["n_errors"],
        "preview_complete": preview["complete"],
        "applied": False,
    }

    # Prefer existing valid canonical; optionally refresh transactionally
    dest = root / "reports" / "phase5" / "build_table_canonical.json"
    if apply_migration:
        mig = migrate_phase5_build_table(root=root, apply=True, require_complete=True)
        migration_meta["applied"] = mig.get("applied", False)
        migration_meta["refusal_reason"] = mig.get("refusal_reason")
    elif not dest.is_file() and preview["complete"]:
        mig = migrate_phase5_build_table(root=root, apply=True, require_complete=True)
        migration_meta["applied"] = mig.get("applied", False)

    try:
        raw_builds = load_canonical_builds(root)
    except (FileNotFoundError, IncompleteBuildRecordError) as exc:
        # Fall back to preview builds only if complete  -  never write empty
        if preview["complete"]:
            raw_builds = preview["builds"]
            migration_meta["used_preview_builds"] = True
        else:
            return {
                "phase": 8 if mode == MODE_INTEGRITY_ONLY else 7,
                "task": "phase5_sequence_reproducibility_audit",
                "mode": mode,
                "overall_status": "MISSING_EVIDENCE",
                "integrity_status": "MISSING_EVIDENCE",
                "scientific_status": None,
                "claims_statistical_reproduction": False,
                "error": str(exc),
                "research_dependencies": deps,
                "migration_preview": {
                    "n_canonical": preview["n_canonical"],
                    "n_errors": preview["n_errors"],
                    "sample_errors": preview["errors"][:5],
                },
                "metaeditor_required": False,
            }

    builds = validate_build_records(raw_builds, project_root=root)

    published_path = root / "reports" / "phase5" / "sequence_research.json"
    published = (
        json.loads(published_path.read_text(encoding="utf-8")) if published_path.is_file() else None
    )
    phase6_path = root / "reports" / "phase6" / "sequence_research_recomputed.json"
    phase6 = (
        json.loads(phase6_path.read_text(encoding="utf-8")) if phase6_path.is_file() else None
    )

    artifact_checks = []
    for b in builds:
        try:
            p = resolve_evidence_path(b.artifact_relpath, root=root, abs_hint=None)
            ok = verify_artifact_sha(p, b.ex5_sha256)
            artifact_checks.append(
                {"artifact_relpath": b.artifact_relpath, "sha_ok": ok, "exists": True}
            )
        except FileNotFoundError as exc:
            artifact_checks.append(
                {
                    "artifact_relpath": b.artifact_relpath,
                    "sha_ok": False,
                    "exists": False,
                    "error": str(exc),
                }
            )

    sha_ok_n = sum(1 for a in artifact_checks if a.get("sha_ok"))
    integrity_status = _integrity_status(sha_ok_n)
    integrity = {
        "n_artifacts_checked": len(artifact_checks),
        "n_sha_ok": sha_ok_n,
        "n_missing": sum(1 for a in artifact_checks if not a.get("exists")),
        "expected": EXPECTED_PHASE5_BUILDS,
        "all_108_verified": sha_ok_n == EXPECTED_PHASE5_BUILDS,
        "status": integrity_status,
    }

    out_dir = root / "reports" / "phase7"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence_integrity.json").write_text(json.dumps(integrity, indent=2), encoding="utf-8")

    comparisons_pub: dict[str, Any] = {}
    comparisons_p6: dict[str, Any] = {}
    means: dict[str, Any] | None = None
    study: dict[str, Any] | None = None
    scientific_status: str | None = None
    scientific_skipped_reason: str | None = None

    if mode == MODE_INTEGRITY_ONLY:
        scientific_skipped_reason = "integrity_only_mode"
        overall = _combine_overall(
            mode=mode,
            integrity_status=integrity_status,
            scientific_status=None,
        )
        audit = {
            "phase": 8,
            "task": "phase5_evidence_integrity_audit",
            "mode": MODE_INTEGRITY_ONLY,
            "overall_status": overall,
            "integrity_status": integrity_status,
            "scientific_status": None,
            "claims_statistical_reproduction": False,
            "scientific_replay_skipped": True,
            "scientific_skipped_reason": scientific_skipped_reason,
            "research_dependencies": deps,
            "script_discrepancy": {
                "finding": (
                    "sequence_research.json was not produced by the versioned script "
                    "path as written (missing build_index on disk). Integrity-only mode verifies "
                    "canonical SHA paths without claiming statistical arm reproduction."
                )
            },
            "migration": migration_meta,
            "canonical_count": len(builds),
            "artifact_checks_summary": integrity,
            "arm_comparisons_vs_phase5_published": {},
            "arm_comparisons_vs_phase6_recomputed": {},
            "recomputed_means": None,
            "recomputed_report": None,
            "random_seed": random_seed,
            "metaeditor_required": False,
            "status_taxonomy_note": (
                "integrity-only never emits arm VERIFIED from LCS stats; "
                "use --full for scientific replay."
            ),
        }
        (out_dir / "evidence_replay.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        return audit

    # Full scientific replay
    if not deps["ok"]:
        scientific_status = "DEPENDENCY_UNAVAILABLE"
        scientific_skipped_reason = "missing_research_dependencies:" + ",".join(deps["missing"])
        # Still attempt study so arm rows carry DEPENDENCY_UNAVAILABLE / RESOURCE_LIMIT
        # rather than fabricating NOT_REPRODUCIBLE means  -  but label clearly up front.
        study = run_sequence_study(builds, root=root, random_seed=random_seed)
        means = summarize_arm_means(study)
        if published:
            for arm in _ARM_NAMES:
                comparisons_pub[arm] = compare_arm_means(
                    published.get(arm), (study.get("arms") or {}).get(arm)
                )
        if phase6:
            p6_arms = phase6.get("arms") or phase6
            for arm in _ARM_NAMES:
                comparisons_p6[arm] = compare_arm_means(
                    p6_arms.get(arm) if isinstance(p6_arms, dict) else None,
                    (study.get("arms") or {}).get(arm),
                )
        # Force scientific rollup to dependency status even if some tiny arms
        # happened to fall back to naive successfully.
        arm_statuses = [c.get("status") for c in comparisons_pub.values()]
        rolled = _aggregate_scientific_status(arm_statuses) if arm_statuses else "DEPENDENCY_UNAVAILABLE"
        if rolled not in {"DEPENDENCY_UNAVAILABLE", "RESOURCE_LIMIT"}:
            scientific_status = "DEPENDENCY_UNAVAILABLE"
        else:
            scientific_status = rolled
    else:
        study = run_sequence_study(builds, root=root, random_seed=random_seed)
        means = summarize_arm_means(study)
        if published:
            for arm in _ARM_NAMES:
                comparisons_pub[arm] = compare_arm_means(
                    published.get(arm), (study.get("arms") or {}).get(arm)
                )
        if phase6:
            p6_arms = phase6.get("arms") or phase6
            for arm in _ARM_NAMES:
                comparisons_p6[arm] = compare_arm_means(
                    p6_arms.get(arm) if isinstance(p6_arms, dict) else None,
                    (study.get("arms") or {}).get(arm),
                )
        statuses = (
            [c.get("status") for c in comparisons_pub.values()]
            if comparisons_pub
            else ["MISSING_EVIDENCE"]
        )
        scientific_status = _aggregate_scientific_status(statuses)

    recomputed_path = out_dir / "sequence_research_recomputed.json"
    recomputed_path.write_text(json.dumps(study, indent=2), encoding="utf-8")

    overall = _combine_overall(
        mode=mode,
        integrity_status=integrity_status,
        scientific_status=scientific_status,
    )

    audit = {
        "phase": 8,
        "task": "phase5_sequence_reproducibility_audit",
        "mode": MODE_FULL,
        "overall_status": overall,
        "integrity_status": integrity_status,
        "scientific_status": scientific_status,
        "claims_statistical_reproduction": scientific_status == "VERIFIED",
        "scientific_replay_skipped": False,
        "scientific_skipped_reason": scientific_skipped_reason,
        "research_dependencies": deps,
        "script_discrepancy": {
            "finding": (
                "sequence_research.json was not produced by the versioned script "
                "path as written (missing build_index on disk). Phase 7/8 replays from "
                "canonical portable paths."
            )
        },
        "migration": migration_meta,
        "canonical_count": len(builds),
        "artifact_checks_summary": integrity,
        "arm_comparisons_vs_phase5_published": comparisons_pub,
        "arm_comparisons_vs_phase6_recomputed": comparisons_p6,
        "recomputed_means": means,
        "recomputed_report": "reports/phase7/sequence_research_recomputed.json",
        "random_seed": random_seed,
        "metaeditor_required": False,
        "status_taxonomy_note": (
            "DEPENDENCY_UNAVAILABLE / RESOURCE_LIMIT are not NOT_REPRODUCIBLE; "
            "NOT_REPRODUCIBLE means LCS means disagreed after a complete replay."
        ),
        "discrepancy_hypotheses": [
            "same_source group selection order differs across runs",
            "algorithm version (naive vs pydivsufsort/int32) shifts LCS length",
            "holdout sample subset of 5 may differ by dict iteration order",
            "historical published means from out-of-band invocation",
        ],
    }
    (out_dir / "evidence_replay.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit
