"""Experiment completeness validation and decision vocabulary."""

from __future__ import annotations

from typing import Any, Sequence

DECISION_POSITIVE_REPLICATED = "POSITIVE_SIGNAL_REPLICATED"
DECISION_POSITIVE_PRELIMINARY = "POSITIVE_SIGNAL_PRELIMINARY"
DECISION_NO_POSITIVE = "NO_POSITIVE_EVIDENCE"
DECISION_INCONCLUSIVE = "INCONCLUSIVE"
DECISION_INVALID = "INVALID_EXPERIMENT"
DEPRECATED_NO_POWER = "NO_FOR_TESTED_FEATURES_WITH_VALID_POWER"


def validate_expected_builds(
    *,
    expected_groups: Sequence[str],
    replicates_per_group: int,
    build_records: Sequence[dict[str, Any]],
    group_key: str = "group_id",
    ok_statuses: Sequence[str] = ("verified", "ran"),
) -> dict[str, Any]:
    expected = sorted(set(expected_groups))
    need = len(expected) * replicates_per_group
    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in expected}
    unexpected = []
    for rec in build_records:
        g = rec.get(group_key)
        if g not in by_group:
            unexpected.append(g)
            continue
        by_group[g].append(rec)
    missing = []
    failed = []
    for g in expected:
        ok_recs = [
            r
            for r in by_group[g]
            if r.get("compile_status") in ok_statuses and r.get("ex5_sha256")
        ]
        if len(ok_recs) < replicates_per_group:
            missing.append({"group_id": g, "ok_builds": len(ok_recs), "required": replicates_per_group})
        for r in by_group[g]:
            if r.get("compile_status") not in ok_statuses or not r.get("ex5_sha256"):
                failed.append(r)
    complete = len(missing) == 0 and need > 0
    return {
        "ok": complete,
        "status": "COMPLETE" if complete else "INCOMPLETE_EXPERIMENT",
        "expected_groups": expected,
        "replicates_per_group": replicates_per_group,
        "expected_builds": need,
        "recorded_builds": len(build_records),
        "missing_or_short_groups": missing,
        "failed_builds": len(failed),
        "unexpected_groups": sorted({g for g in unexpected if g}),
        "decision_if_incomplete": DECISION_INVALID,
        "note": "Do not emit decisive semantic conclusions from an incomplete build matrix.",
    }


def classify_semantic_outcome(
    *,
    experiment_complete: bool,
    heldout_balanced_accuracy: float | None,
    majority_balanced_accuracy: float | None,
    permutation_p: float | None,
    size_only_balanced_accuracy: float | None,
    independently_replicated: bool,
    n_holdout_groups: int,
    min_holdout_for_strong: int = 20,
) -> dict[str, Any]:
    if not experiment_complete:
        return {
            "decision": DECISION_INVALID,
            "rationale": ["Build matrix incomplete or invalid design."],
        }
    if heldout_balanced_accuracy is None or majority_balanced_accuracy is None:
        return {"decision": DECISION_INCONCLUSIVE, "rationale": ["Missing primary metrics."]}

    above_maj = heldout_balanced_accuracy > majority_balanced_accuracy + 0.05
    above_null = permutation_p is not None and permutation_p < 0.05
    size_explains = (
        size_only_balanced_accuracy is not None
        and size_only_balanced_accuracy >= heldout_balanced_accuracy - 0.05
        and size_only_balanced_accuracy > majority_balanced_accuracy + 0.05
    )

    if above_maj and above_null and not size_explains:
        if independently_replicated and n_holdout_groups >= min_holdout_for_strong:
            return {
                "decision": DECISION_POSITIVE_REPLICATED,
                "rationale": [
                    "Held-out metric exceeds majority and permutation null; "
                    "independent replication succeeded; size-only does not fully explain."
                ],
            }
        return {
            "decision": DECISION_POSITIVE_PRELIMINARY,
            "rationale": [
                "Preliminary held-out association above baselines; "
                "requires independent replication before POSITIVE_SIGNAL_REPLICATED."
            ],
        }

    if n_holdout_groups < min_holdout_for_strong:
        return {
            "decision": DECISION_INCONCLUSIVE,
            "rationale": [
                f"n_holdout_groups={n_holdout_groups} < {min_holdout_for_strong}; "
                "insufficient for strong negative or power-based absence claims."
            ],
            "absence_of_positive_evidence": True,
            "legacy_deprecated_label": DEPRECATED_NO_POWER,
        }

    return {
        "decision": DECISION_NO_POSITIVE,
        "rationale": [
            "No held-out association above majority/permutation criteria for tested features; "
            "does not prove absence of recoverable information under other representations."
        ],
    }