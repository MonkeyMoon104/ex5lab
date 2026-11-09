"""Group-aware supervised evaluation for post-header EX5 features ."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Any, Sequence

from ex5lab.analysis.eval_design import (
    INVALID_EVALUATION_DESIGN,
    SampleRow,
    validate_supervised_design,
)


def _mean_std(cols: list[list[float]]) -> tuple[list[float], list[float]]:
    n = len(cols[0]) if cols else 0
    means = []
    stds = []
    for j in range(n):
        vals = [row[j] for row in cols]
        m = sum(vals) / len(vals) if vals else 0.0
        var = sum((v - m) ** 2 for v in vals) / len(vals) if vals else 0.0
        s = math.sqrt(var)
        means.append(m)
        stds.append(s if s > 1e-12 else 1.0)  # zero-variance -> scale 1, later zeroed
    return means, stds


def fit_scaler(train_vecs: list[list[float]]) -> dict[str, Any]:
    means, stds = _mean_std(train_vecs)
    zero_var = [i for i, s in enumerate(stds) if abs(s - 1.0) < 1e-15 and all(abs(row[i] - means[i]) < 1e-15 for row in train_vecs)]
    # recompute true zero var
    zero_var = []
    for j in range(len(means)):
        vals = [row[j] for row in train_vecs]
        if max(vals) - min(vals) < 1e-15:
            zero_var.append(j)
            stds[j] = 1.0
    return {"mean": means, "std": stds, "zero_variance_columns": zero_var, "n_features": len(means)}


def apply_scaler(vec: list[float], scaler: dict[str, Any]) -> list[float]:
    out = []
    for j, v in enumerate(vec):
        if j in scaler["zero_variance_columns"]:
            out.append(0.0)
        else:
            out.append((v - scaler["mean"][j]) / scaler["std"][j])
    return out


def l2(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(min(len(a), len(b)))))


def confusion_and_scores(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict[str, Any]:
    cm = {a: {b: 0 for b in labels} for a in labels}
    for t, p in zip(y_true, y_pred):
        if t in cm and p in cm[t]:
            cm[t][p] += 1
        elif t in cm:
            cm[t][p] = cm[t].get(p, 0) + 1
    # per-class recall/precision
    recalls = []
    precisions = []
    f1s = []
    support = {}
    for lab in labels:
        tp = cm[lab].get(lab, 0)
        fn = sum(cm[lab].get(b, 0) for b in labels) - tp
        fp = sum(cm[a].get(lab, 0) for a in labels if a != lab)
        support[lab] = tp + fn
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        recalls.append(rec)
        precisions.append(prec)
        f1s.append(f1)
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    acc = correct / len(y_true) if y_true else 0.0
    bal = sum(recalls) / len(recalls) if recalls else 0.0
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    return {
        "accuracy": round(acc, 6),
        "balanced_accuracy": round(bal, 6),
        "macro_f1": round(macro_f1, 6),
        "support": support,
        "confusion_matrix": cm,
        "per_class_recall": {lab: round(recalls[i], 6) for i, lab in enumerate(labels)},
        "per_class_precision": {lab: round(precisions[i], 6) for i, lab in enumerate(labels)},
        "per_class_f1": {lab: round(f1s[i], 6) for i, lab in enumerate(labels)},
    }


def majority_baseline(train_labels: list[str], test_labels: list[str]) -> dict[str, Any]:
    maj = Counter(train_labels).most_common(1)[0][0]
    preds = [maj] * len(test_labels)
    labels = sorted(set(train_labels) | set(test_labels))
    return {"majority_label": maj, **confusion_and_scores(test_labels, preds, labels)}


def knn_predict(
    train_vecs: list[list[float]],
    train_labels: list[str],
    query: list[float],
    *,
    k: int = 1,
) -> str:
    dists = [(l2(query, tv), lab) for tv, lab in zip(train_vecs, train_labels)]
    dists.sort(key=lambda x: x[0])
    top = dists[:k]
    votes = Counter(lab for _, lab in top)
    # tie-break: nearest label
    return votes.most_common(1)[0][0]


def aggregate_group_vectors(
    rows: list[SampleRow],
    vec_fn,
) -> tuple[list[str], list[str], list[list[float]]]:
    """Mean-pool feature vectors within each group (source-level primary metric)."""
    buckets: dict[str, list[list[float]]] = defaultdict(list)
    labels: dict[str, str] = {}
    for r in rows:
        buckets[r.group_id].append(vec_fn(r))
        labels[r.group_id] = r.label
    gids = sorted(buckets.keys())
    vecs = []
    labs = []
    for g in gids:
        mats = buckets[g]
        n = len(mats[0])
        mean_v = [sum(m[j] for m in mats) / len(mats) for j in range(n)]
        vecs.append(mean_v)
        labs.append(labels[g])
    return gids, labs, vecs


def evaluate_heldout(
    rows: Sequence[SampleRow],
    *,
    train_groups: set[str],
    test_groups: set[str],
    vectorize,
    k: int = 1,
    seed: int = 0,
    n_permutations: int = 200,
) -> dict[str, Any]:
    design = validate_supervised_design(
        rows,
        train_groups=train_groups,
        test_groups=test_groups,
        min_train_groups_per_class=2,
        min_test_groups_per_class=1,
    )
    if not design["ok"]:
        return {
            "ok": False,
            "status": INVALID_EVALUATION_DESIGN,
            "design": design,
            "note": "Refusing to emit a fake accuracy headline for an invalid evaluation design.",
        }

    train_rows = [r for r in rows if r.group_id in train_groups]
    test_rows = [r for r in rows if r.group_id in test_groups]

    # Fit scaler on train builds only (all replicates)
    train_raw = [vectorize(r) for r in train_rows]
    scaler = fit_scaler(train_raw)

    def scaled(r: SampleRow) -> list[float]:
        return apply_scaler(vectorize(r), scaler)

    # Per-build evaluation (secondary)
    tr_vecs_b = [scaled(r) for r in train_rows]
    tr_labs_b = [r.label for r in train_rows]
    te_vecs_b = [scaled(r) for r in test_rows]
    te_labs_b = [r.label for r in test_rows]
    preds_b = [knn_predict(tr_vecs_b, tr_labs_b, q, k=k) for q in te_vecs_b]
    labels = sorted(set(tr_labs_b) | set(te_labs_b))
    per_build = confusion_and_scores(te_labs_b, preds_b, labels)

    # Per-unique-source (primary): mean-pool within group
    tr_gids, tr_labs_g, tr_raw_g = aggregate_group_vectors(train_rows, vectorize)
    te_gids, te_labs_g, te_raw_g = aggregate_group_vectors(test_rows, vectorize)
    tr_vecs_g = [apply_scaler(v, scaler) for v in tr_raw_g]
    te_vecs_g = [apply_scaler(v, scaler) for v in te_raw_g]
    preds_g = [knn_predict(tr_vecs_g, tr_labs_g, q, k=k) for q in te_vecs_g]
    per_source = confusion_and_scores(te_labs_g, preds_g, labels)
    per_source["test_group_ids"] = te_gids
    per_source["predictions"] = [
        {"group_id": g, "true": t, "pred": p} for g, t, p in zip(te_gids, te_labs_g, preds_g)
    ]

    maj = majority_baseline(tr_labs_g, te_labs_g)

    # Group-respecting label permutations on train group labels; score test with shuffled train labels
    rng = random.Random(seed)
    null_scores = []
    # permute labels across train groups (keep group feature vectors fixed)
    for _ in range(n_permutations):
        perm_labs = tr_labs_g[:]
        rng.shuffle(perm_labs)
        preds_n = [knn_predict(tr_vecs_g, perm_labs, q, k=k) for q in te_vecs_g]
        null_scores.append(confusion_and_scores(te_labs_g, preds_n, labels)["balanced_accuracy"])
    obs = per_source["balanced_accuracy"]
    # one-sided: fraction of null >= observed
    p_emp = (sum(1 for s in null_scores if s >= obs - 1e-15) + 1) / (len(null_scores) + 1)

    return {
        "ok": True,
        "status": "OK",
        "seed": seed,
        "k": k,
        "design": design,
        "scaler": {
            "n_features": scaler["n_features"],
            "zero_variance_columns": scaler["zero_variance_columns"],
            "fit_on": "train_builds_only",
        },
        "per_build_metrics": per_build,
        "per_source_metrics": per_source,
        "majority_baseline_per_source": maj,
        "permutation_null": {
            "n_permutations": n_permutations,
            "group_respecting": True,
            "observed_balanced_accuracy": obs,
            "null_mean": round(sum(null_scores) / len(null_scores), 6) if null_scores else None,
            "null_max": round(max(null_scores), 6) if null_scores else None,
            "empirical_p_one_sided": round(p_emp, 6),
            "note": (
                "With small held-out group counts, p-values have low resolution; "
                "treat as descriptive unless n_test_groups is large."
            ),
        },
        "primary_metric": "per_source_balanced_accuracy",
        "primary_value": obs,
    }


def pairwise_distance_summary(
    rows: Sequence[SampleRow],
    vectorize,
    scaler: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Within-source, within-class-across-source, between-class distances."""
    def vec(r: SampleRow) -> list[float]:
        v = vectorize(r)
        return apply_scaler(v, scaler) if scaler else v

    within_source = []
    by_group: dict[str, list[SampleRow]] = defaultdict(list)
    for r in rows:
        by_group[r.group_id].append(r)
    for g, rs in by_group.items():
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                within_source.append(l2(vec(rs[i]), vec(rs[j])))

    # group means
    gids, labs, gvecs = aggregate_group_vectors(list(rows), lambda r: vec(r) if scaler is None else apply_scaler(vectorize(r), scaler))
    # actually aggregate_group_vectors calls vec_fn on rows - pass vectorize then scale outside
    gids, labs, raw_g = aggregate_group_vectors(list(rows), vectorize)
    if scaler:
        gvecs = [apply_scaler(v, scaler) for v in raw_g]
    else:
        gvecs = raw_g

    within_class = []
    between_class = []
    for i in range(len(gids)):
        for j in range(i + 1, len(gids)):
            d = l2(gvecs[i], gvecs[j])
            if labs[i] == labs[j]:
                within_class.append(d)
            else:
                between_class.append(d)

    def stats(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"n": 0, "mean": None, "min": None, "max": None}
        return {
            "n": len(xs),
            "mean": round(sum(xs) / len(xs), 6),
            "min": round(min(xs), 6),
            "max": round(max(xs), 6),
        }

    return {
        "within_source_replicates": stats(within_source),
        "within_class_across_sources": stats(within_class),
        "between_class": stats(between_class),
    }