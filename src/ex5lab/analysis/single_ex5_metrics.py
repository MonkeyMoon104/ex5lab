"""metrics: single-EX5 primary vs rebuild-aggregated secondary."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from ex5lab.analysis.eval_design import SampleRow, validate_supervised_design
from ex5lab.analysis.supervised_eval import (
    apply_scaler,
    confusion_and_scores,
    evaluate_heldout,
    fit_scaler,
    knn_predict,
    majority_baseline,
)


def evaluate_single_and_aggregated(
    rows: Sequence[SampleRow],
    *,
    train_groups: set[str],
    test_groups: set[str],
    vectorize: Callable[[SampleRow], list[float]],
    seed: int = 51,
    n_permutations: int = 500,
) -> dict[str, Any]:
    """Primary: each holdout EX5 scored independently; Secondary: source mean-pool."""
    design = validate_supervised_design(
        rows,
        train_groups=train_groups,
        test_groups=test_groups,
        min_train_groups_per_class=2,
        min_test_groups_per_class=1,
    )
    if not design["ok"]:
        return {"ok": False, "status": design["status"], "design": design}

    # Aggregated (existing)
    agg = evaluate_heldout(
        rows,
        train_groups=train_groups,
        test_groups=test_groups,
        vectorize=vectorize,
        seed=seed,
        n_permutations=n_permutations,
    )

    # Single-build: train on all train replicates; predict each test replicate
    train_rows = [r for r in rows if r.group_id in train_groups]
    test_rows = [r for r in rows if r.group_id in test_groups]
    scaler = fit_scaler([vectorize(r) for r in train_rows])
    tr_vecs = [apply_scaler(vectorize(r), scaler) for r in train_rows]
    tr_labs = [r.label for r in train_rows]
    te_vecs = [apply_scaler(vectorize(r), scaler) for r in test_rows]
    te_labs = [r.label for r in test_rows]
    preds = [knn_predict(tr_vecs, tr_labs, q, k=1) for q in te_vecs]
    labels = sorted(set(tr_labs) | set(te_labs))
    single = confusion_and_scores(te_labs, preds, labels)
    # Per-source variance of single-build correctness
    by_group: dict[str, list[bool]] = {}
    for r, pred in zip(test_rows, preds):
        by_group.setdefault(r.group_id, []).append(pred == r.label)
    group_acc = {g: sum(v) / len(v) for g, v in by_group.items()}
    maj = majority_baseline(tr_labs, te_labs)

    return {
        "ok": True,
        "design": design,
        "primary_single_ex5": {
            **single,
            "n_test_ex5": len(test_rows),
            "n_test_groups": len(test_groups),
            "note": "Production-relevance metric: one EX5 per prediction; replicates are not independent programs.",
            "per_group_accuracy": group_acc,
            "majority_baseline": maj,
        },
        "secondary_source_aggregated": {
            "per_source_metrics": agg.get("per_source_metrics"),
            "permutation_null": agg.get("permutation_null"),
            "majority_baseline_per_source": agg.get("majority_baseline_per_source"),
            "note": "Diagnostic only when multiple compiles of same source are available.",
        },
        "full_aggregated_eval": agg,
    }