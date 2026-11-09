"""Evaluation design validation and group-aware supervised metrics ."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

INVALID_EVALUATION_DESIGN = "INVALID_EVALUATION_DESIGN"


@dataclass(frozen=True)
class SampleRow:
    sample_id: str
    group_id: str  # canonical source/template; never split across train/test
    label: str
    features: dict[str, Any]
    build_index: int = 1
    source_sha256: str | None = None
    ex5_sha256: str | None = None


def validate_supervised_design(
    rows: Sequence[SampleRow],
    *,
    train_groups: set[str],
    test_groups: set[str],
    min_classes: int = 2,
    min_train_groups_per_class: int = 2,
    min_test_groups_per_class: int = 1,
    require_shared_label_space: bool = True,
) -> dict[str, Any]:
    """Reject singleton-label / absent-class / leakage designs before scoring."""
    errors: list[str] = []
    if train_groups & test_groups:
        errors.append(f"group leakage between train and test: {sorted(train_groups & test_groups)}")

    by_group = {r.group_id: r.label for r in rows}
    # consistent labels within group
    lab_by_group: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        lab_by_group[r.group_id].add(r.label)
    for g, labs in lab_by_group.items():
        if len(labs) > 1:
            errors.append(f"group {g} has multiple labels: {sorted(labs)}")

    train_rows = [r for r in rows if r.group_id in train_groups]
    test_rows = [r for r in rows if r.group_id in test_groups]
    if not train_rows or not test_rows:
        errors.append("train or test partition empty")

    train_labels = {r.label for r in train_rows}
    test_labels = {r.label for r in test_rows}
    if require_shared_label_space and (test_labels - train_labels):
        errors.append(
            f"test labels absent from train (shared label space required): {sorted(test_labels - train_labels)}"
        )

    # groups per class
    def groups_per_class(subset: list[SampleRow]) -> dict[str, set[str]]:
        d: dict[str, set[str]] = defaultdict(set)
        for r in subset:
            d[r.label].add(r.group_id)
        return d

    tr_gpc = groups_per_class(train_rows)
    te_gpc = groups_per_class(test_rows)
    if len(train_labels) < min_classes:
        errors.append(f"need >= {min_classes} train classes, got {len(train_labels)}")

    for lab, gs in tr_gpc.items():
        if len(gs) < min_train_groups_per_class:
            errors.append(
                f"class {lab!r} has only {len(gs)} train group(s); need >= {min_train_groups_per_class} "
                f"(singleton-class LOO is INVALID_EVALUATION_DESIGN)"
            )
    for lab in train_labels:
        if lab not in te_gpc or len(te_gpc[lab]) < min_test_groups_per_class:
            errors.append(
                f"class {lab!r} missing from test groups (need >= {min_test_groups_per_class} held-out template(s))"
            )

    # Detect classic Phase-3 failure mode: one group per label overall + LOO intent
    overall_gpc = groups_per_class(list(rows))
    if all(len(gs) == 1 for gs in overall_gpc.values()) and len(overall_gpc) >= 2:
        errors.append(
            "one source-group per class across corpus: leave-one-out 1-NN cannot have a same-label neighbor "
            f"({INVALID_EVALUATION_DESIGN})"
        )

    ok = not errors
    return {
        "ok": ok,
        "status": "OK" if ok else INVALID_EVALUATION_DESIGN,
        "errors": errors,
        "n_rows": len(rows),
        "n_train_rows": len(train_rows),
        "n_test_rows": len(test_rows),
        "train_groups": sorted(train_groups),
        "test_groups": sorted(test_groups),
        "train_labels": sorted(train_labels),
        "test_labels": sorted(test_labels),
        "train_groups_per_class": {k: sorted(v) for k, v in tr_gpc.items()},
        "test_groups_per_class": {k: sorted(v) for k, v in te_gpc.items()},
        "class_balance_train_rows": dict(Counter(r.label for r in train_rows)),
        "class_balance_test_rows": dict(Counter(r.label for r in test_rows)),
        "class_balance_train_groups": {k: len(v) for k, v in tr_gpc.items()},
        "class_balance_test_groups": {k: len(v) for k, v in te_gpc.items()},
    }


def validate_loo_feasibility(rows: Sequence[SampleRow]) -> dict[str, Any]:
    """Reject LOO when each class has only one group ."""
    gpc: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        gpc[r.label].add(r.group_id)
    if not rows:
        return {"ok": False, "status": INVALID_EVALUATION_DESIGN, "errors": ["empty rows"]}
    if any(len(gs) < 2 for gs in gpc.values()):
        return {
            "ok": False,
            "status": INVALID_EVALUATION_DESIGN,
            "errors": [
                "LOO/1-NN requires >=2 independent groups per class; "
                f"groups_per_class={{{', '.join(f'{k}:{len(v)}' for k,v in sorted(gpc.items()))}}}"
            ],
            "groups_per_class": {k: sorted(v) for k, v in gpc.items()},
        }
    return {"ok": True, "status": "OK", "errors": [], "groups_per_class": {k: sorted(v) for k, v in gpc.items()}}