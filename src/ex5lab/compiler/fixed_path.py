"""Fixed-path / variable-path MetaEditor harness with secure path containment."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from ex5lab.compiler.env import discover_metaeditor, discover_mql5_include
from ex5lab.compiler.version import provenance_record
from ex5lab.experiment.compile_util import compile_target, sha256_file

DEFAULT_FIXED_REL = Path("Scripts") / "ex5lab_fixed" / "unit_a" / "prog.mq5"


class UnauthorizedStagingPathError(ValueError):
    """Staging path is outside the authorized MQL5 root."""


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _lexically_normalize(path: Path) -> Path:
    """Collapse . and .. without filesystem access / symlink follow."""
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise UnauthorizedStagingPathError("path escapes with '..'")
            if len(parts) == 1 and parts[0].endswith(":"):
                raise UnauthorizedStagingPathError("path escapes drive root with '..'")
            if parts[-1] == "..":
                raise UnauthorizedStagingPathError("invalid '..' sequence")
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise UnauthorizedStagingPathError("empty path after normalize")
    return Path(*parts)


def _normcase_key(path: Path) -> str:
    return os.path.normcase(str(path))


def is_path_within(root: Path, candidate: Path) -> bool:
    """Return True iff candidate is root or a descendant (no string-prefix checks)."""
    root_n = Path(root).resolve()
    cand_n = Path(candidate).resolve()
    if _normcase_key(cand_n) == _normcase_key(root_n):
        return True
    try:
        cand_n.relative_to(root_n)
        return True
    except ValueError:
        # Windows case-insensitive fallback when relative_to is case-sensitive
        try:
            Path(_normcase_key(cand_n)).relative_to(Path(_normcase_key(root_n)))
            return True
        except ValueError:
            return False


def authorize_staging_path(include_root: Path, staging: Path) -> Path:
    """Authorize a staging file path under include_root; do not create directories.

    Uses lexical normalize for non-existing paths, then resolve + relative_to
    when the path (or parents) exist so junction/symlink escapes are rejected.
    Never uses string startswith containment.
    """
    include_root = Path(include_root)
    staging = Path(staging)
    root_r = include_root.resolve()

    if staging.is_absolute():
        intended = _lexically_normalize(staging)
    else:
        intended = _lexically_normalize(root_r.joinpath(*staging.parts))

    # Lexical ancestry (handles not-yet-created paths)
    try:
        intended.relative_to(_lexically_normalize(root_r))
    except ValueError as exc:
        raise UnauthorizedStagingPathError(
            f"staging path escapes authorized MQL5 root: intended={intended} root={root_r}"
        ) from exc

    # If any ancestor exists, resolve and re-check (catches junctions/symlinks)
    probe = intended
    while True:
        if probe.exists() or probe.is_symlink():
            resolved = probe.resolve()
            if not is_path_within(root_r, resolved):
                raise UnauthorizedStagingPathError(
                    f"staging resolves outside authorized MQL5 root: "
                    f"intended={intended} resolved={resolved} root={root_r}"
                )
            break
        if probe == probe.parent:
            break
        probe = probe.parent

    # Final resolved check when the leaf exists
    if intended.exists() or intended.is_symlink():
        resolved_leaf = intended.resolve()
        if not is_path_within(root_r, resolved_leaf):
            raise UnauthorizedStagingPathError(
                f"staging resolves outside authorized MQL5 root: "
                f"intended={intended} resolved={resolved_leaf} root={root_r}"
            )
        return resolved_leaf

    return intended


def ensure_under_mql5(include_root: Path, rel: Path) -> Path:
    """Authorize then create staging path under include_root.

    Rejects sibling-prefix collisions (MQL5 vs MQL5_evil), absolute escapes,
    '..' traversal, and symlink/junction escapes when resolvable.
    Directories are created only after authorization.
    """
    intended = authorize_staging_path(include_root, rel)
    intended.parent.mkdir(parents=True, exist_ok=True)
    # Re-authorize after mkdir in case a race planted a junction
    return authorize_staging_path(include_root, intended)


def compile_at_path(
    source_mq5: Path,
    *,
    staging_mq5: Path,
    evidence_ex5: Path,
    metaeditor: Path,
    include: Path,
    experiment_id: str,
    keep_staging_source: bool = True,
) -> dict[str, Any]:
    source_mq5 = Path(source_mq5)
    evidence_ex5 = Path(evidence_ex5)
    include_r = Path(include).resolve()

    # Single auth path - never mkdir before authorize_staging_path succeeds
    staging_mq5 = authorize_staging_path(include_r, Path(staging_mq5))
    staging_mq5.parent.mkdir(parents=True, exist_ok=True)
    staging_mq5 = authorize_staging_path(include_r, staging_mq5)

    src_sha = sha256_file(source_mq5)
    shutil.copy2(source_mq5, staging_mq5)
    staged_sha = sha256_file(staging_mq5)
    if staged_sha != src_sha:
        raise RuntimeError("staging source SHA mismatch")

    staging_mq5.with_suffix(".ex5").unlink(missing_ok=True)
    staging_mq5.with_suffix(".log").unlink(missing_ok=True)

    rec = compile_target(
        staging_mq5,
        out_ex5=evidence_ex5,
        metaeditor=metaeditor,
        include=include,
        optimize_setting="cli_default",
    )
    record = {
        "experiment_id": experiment_id,
        "source_path": str(source_mq5),
        "source_sha256": src_sha,
        "staging_mq5": str(staging_mq5),
        "staging_sha256": staged_sha,
        "staging_abs_dir": str(staging_mq5.parent.resolve()),
        "staging_filename": staging_mq5.name,
        "evidence_ex5": rec.get("output_ex5"),
        "ex5_sha256": rec.get("ex5_sha256"),
        "ex5_size": rec.get("ex5_size"),
        "compile_status": rec.get("status"),
        "log_result_line": rec.get("log_result_line"),
        "fresh_mtime_confirmed": rec.get("fresh_mtime_confirmed"),
        "started_utc": rec.get("started_utc"),
        "ended_utc": rec.get("ended_utc"),
        "metaeditor": str(metaeditor),
        "include": str(include),
        "optimize_setting": "cli_default",
    }
    _write_json(evidence_ex5.with_suffix(".compile.json"), {**rec, "harness": record})
    return record


def run_fixed_path_series(
    source_mq5: Path,
    *,
    n: int,
    evidence_dir: Path,
    series_id: str,
    staging_rel: Path | None = None,
    metaeditor: Path | None = None,
    include: Path | None = None,
) -> dict[str, Any]:
    me = discover_metaeditor(metaeditor)
    inc = discover_mql5_include(include)
    if not me["exists"] or not inc["exists"]:
        return {"ok": False, "status": "INVALID_EXPERIMENT", "reason": "compiler unavailable"}
    metaeditor_p = Path(me["path"])
    include_p = Path(inc["path"])
    staging = ensure_under_mql5(include_p, staging_rel or DEFAULT_FIXED_REL)
    prov = provenance_record(metaeditor=metaeditor_p)
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    builds = []
    for i in range(1, n + 1):
        eid = f"{series_id}_fixed_r{i:02d}"
        out = evidence_dir / f"{eid}.ex5"
        builds.append(
            compile_at_path(
                source_mq5,
                staging_mq5=staging,
                evidence_ex5=out,
                metaeditor=metaeditor_p,
                include=include_p,
                experiment_id=eid,
            )
        )
        time.sleep(0.12)
    return {
        "ok": all(b.get("ex5_sha256") for b in builds),
        "series_id": series_id,
        "mode": "fixed_path",
        "staging_mq5": str(staging),
        "n_requested": n,
        "n_ok": sum(1 for b in builds if b.get("ex5_sha256")),
        "compiler_provenance": prov,
        "builds": builds,
        "unique_ex5_hashes": len({b["ex5_sha256"] for b in builds if b.get("ex5_sha256")}),
        "unique_sizes": sorted({b["ex5_size"] for b in builds if b.get("ex5_size") is not None}),
    }


def run_variable_path_series(
    source_mq5: Path,
    *,
    n: int,
    evidence_dir: Path,
    series_id: str,
    path_variants: list[Path],
    metaeditor: Path | None = None,
    include: Path | None = None,
) -> dict[str, Any]:
    me = discover_metaeditor(metaeditor)
    inc = discover_mql5_include(include)
    if not me["exists"] or not inc["exists"]:
        return {"ok": False, "status": "INVALID_EXPERIMENT", "reason": "compiler unavailable"}
    metaeditor_p = Path(me["path"])
    include_p = Path(inc["path"])
    prov = provenance_record(metaeditor=metaeditor_p)
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    builds = []
    for i in range(1, n + 1):
        rel = path_variants[(i - 1) % len(path_variants)]
        staging = ensure_under_mql5(include_p, rel)
        out = evidence_dir / f"{series_id}_var_r{i:02d}.ex5"
        rec = compile_at_path(
            source_mq5,
            staging_mq5=staging,
            evidence_ex5=out,
            metaeditor=metaeditor_p,
            include=include_p,
            experiment_id=f"{series_id}_var_r{i:02d}",
        )
        rec["path_variant_rel"] = str(rel).replace("\\", "/")
        builds.append(rec)
        time.sleep(0.12)
    return {
        "ok": all(b.get("ex5_sha256") for b in builds),
        "series_id": series_id,
        "mode": "variable_path",
        "n_requested": n,
        "n_ok": sum(1 for b in builds if b.get("ex5_sha256")),
        "compiler_provenance": prov,
        "builds": builds,
        "unique_ex5_hashes": len({b["ex5_sha256"] for b in builds if b.get("ex5_sha256")}),
        "unique_sizes": sorted({b["ex5_size"] for b in builds if b.get("ex5_size") is not None}),
        "unique_staging_dirs": sorted({b["staging_abs_dir"] for b in builds}),
    }