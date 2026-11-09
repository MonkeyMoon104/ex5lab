"""Versioned sequence-research runner with reproducible random controls."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from ex5lab.analysis.sequence import pairwise_sequence_report
from ex5lab.experiment.build_schema import (
    BuildRecord,
    IncompleteBuildRecordError,
    select_by_build_index,
    validate_build_records,
)
from ex5lab.experiment.evidence_paths import project_root_from, resolve_evidence_path, sha256_file


DEFAULT_RANDOM_SEED = 20251104


def load_phase5_canonical_builds(root: Path | None = None) -> list[BuildRecord]:
    """Load builds from the repaired canonical table if present."""
    root = root or project_root_from()
    path = root / "reports" / "phase5" / "build_table_canonical.json"
    if not path.is_file():
        raise FileNotFoundError(
            "reports/phase5/build_table_canonical.json missing  -  run evidence migration/audit first"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_build_records(data["builds"], project_root=root)


def _paths_for(records: list[BuildRecord], root: Path) -> list[str]:
    out = []
    for r in records:
        p = resolve_evidence_path(r.artifact_relpath, root=root, abs_hint=r.evidence_ex5_abs)
        live = sha256_file(p)
        if live != r.ex5_sha256.lower():
            raise ValueError(f"SHA mismatch for {r.artifact_relpath}: {live} != {r.ex5_sha256}")
        out.append(str(p))
    return out


def make_randomized_control_bytes(payload: bytes, *, seed: int) -> bytes:
    rng = random.Random(seed)
    arr = bytearray(payload)
    rng.shuffle(arr)
    return bytes(arr)


def run_sequence_study(
    builds: list[BuildRecord],
    *,
    root: Path | None = None,
    exclude_prefix: int = 744,
    random_seed: int = DEFAULT_RANDOM_SEED,
    holdout_sample: int = 5,
) -> dict[str, Any]:
    """Generate all Phase-5-style sequence arms from validated build records."""
    root = root or project_root_from()
    if not builds:
        raise IncompleteBuildRecordError("no build records")

    # same-source: first train/group with 3 replicates
    by_group: dict[str, list[BuildRecord]] = {}
    for b in builds:
        by_group.setdefault(b.source_group_id, []).append(b)

    same_group = None
    for gid, rows in by_group.items():
        if len(rows) >= 3 and rows[0].split == "train":
            same_group = sorted(rows, key=lambda r: r.build_index)[:3]
            break
    if same_group is None:
        # any group with 3 builds
        for gid, rows in by_group.items():
            if len(rows) >= 3:
                same_group = sorted(rows, key=lambda r: r.build_index)[:3]
                break

    r1 = select_by_build_index(builds, 1)
    present = [b for b in r1 if b.split == "holdout" and b.label == "BRANCH_PRESENT"][:holdout_sample]
    absent = [b for b in r1 if b.split == "holdout" and b.label == "BRANCH_ABSENT"][:holdout_sample]

    report: dict[str, Any] = {
        "schema": "sequence_study_v1",
        "exclude_prefix": exclude_prefix,
        "random_seed": random_seed,
        "provenance": "ex5lab.analysis.sequence_runner.run_sequence_study",
        "arms": {},
    }

    if same_group and len(same_group) >= 2:
        report["arms"]["same_source_rebuilds"] = pairwise_sequence_report(
            _paths_for(same_group, root), exclude_prefix=exclude_prefix, label="same_source_rebuilds"
        )
        report["arms"]["same_source_rebuilds"]["group_id"] = same_group[0].source_group_id
    else:
        report["arms"]["same_source_rebuilds"] = None

    if len(present) >= 2:
        report["arms"]["holdout_present_r1"] = pairwise_sequence_report(
            _paths_for(present, root), exclude_prefix=exclude_prefix, label="present"
        )
    else:
        report["arms"]["holdout_present_r1"] = None

    if len(absent) >= 2:
        report["arms"]["holdout_absent_r1"] = pairwise_sequence_report(
            _paths_for(absent, root), exclude_prefix=exclude_prefix, label="absent"
        )
    else:
        report["arms"]["holdout_absent_r1"] = None

    if present and absent:
        cross = present[:3] + absent[:3]
        if len(cross) >= 2:
            report["arms"]["cross_class_r1"] = pairwise_sequence_report(
                _paths_for(cross, root), exclude_prefix=exclude_prefix, label="cross"
            )
        else:
            report["arms"]["cross_class_r1"] = None
    else:
        report["arms"]["cross_class_r1"] = None

    # Randomized control: shuffle post-header bytes of first present (or first r1)
    seed_rec = present[0] if present else (r1[0] if r1 else None)
    if seed_rec is not None:
        src_path = resolve_evidence_path(
            seed_rec.artifact_relpath, root=root, abs_hint=seed_rec.evidence_ex5_abs
        )
        raw = Path(src_path).read_bytes()
        header = raw[:exclude_prefix]
        payload = raw[exclude_prefix:]
        rnd = make_randomized_control_bytes(payload, seed=random_seed)
        tmp_dir = root / "reports" / "phase6" / "sequence_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tmp_dir / f"rand_control_seed{random_seed}.ex5"
        tmp.write_bytes(header + rnd)
        report["arms"]["randomized_control"] = pairwise_sequence_report(
            [str(src_path), str(tmp)], exclude_prefix=exclude_prefix, label="rand"
        )
        report["arms"]["randomized_control"]["seed"] = random_seed
        report["arms"]["randomized_control"]["control_artifact"] = str(
            tmp.relative_to(root)
        ).replace(chr(92), '/')
    else:
        report["arms"]["randomized_control"] = None

    return report


def summarize_arm_means(study: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for name, arm in (study.get("arms") or {}).items():
        if not arm:
            out[name] = None
            continue
        out[name] = {
            "lcs_mean": (arm.get("lcs") or {}).get("mean_length"),
            "tlsh_mean": (arm.get("tlsh") or {}).get("mean_distance"),
            "completeness": arm.get("completeness"),
        }
    return out
