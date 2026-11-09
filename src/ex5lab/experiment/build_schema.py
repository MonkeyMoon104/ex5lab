"""Canonical build-record schema for EX5 research experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from ex5lab.experiment.path_portability import historical_basename


REQUIRED_FIELDS = (
    "build_index",
    "source_group_id",
    "source_sha256",
    "ex5_sha256",
    "experiment_id",
    "split",
    "label",
    "artifact_relpath",
    "compiler_version",
)


class IncompleteBuildRecordError(ValueError):
    """Build record missing required provenance fields."""


@dataclass
class BuildRecord:
    build_index: int
    source_group_id: str
    source_sha256: str
    ex5_sha256: str
    experiment_id: str
    split: str
    label: str
    artifact_relpath: str
    compiler_version: str
    family: str | None = None
    template_family: str | None = None
    optimize_setting: str | None = None
    staging_mq5: str | None = None
    evidence_ex5_abs: str | None = None
    ex5_size: int | None = None
    compile_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require(rec: dict[str, Any], field: str) -> Any:
    if field not in rec or rec[field] in (None, ""):
        raise IncompleteBuildRecordError(f"missing required field: {field}")
    return rec[field]


def normalize_build_record(rec: dict[str, Any], *, project_root=None) -> BuildRecord:
    """Validate and normalize a build dict. Does not silently invent provenance."""
    del project_root
    rec = dict(rec)
    if "source_group_id" not in rec and rec.get("group_id"):
        rec["source_group_id"] = rec["group_id"]

    for field in REQUIRED_FIELDS:
        _require(rec, field)

    bi = int(rec["build_index"])
    if bi < 1:
        raise IncompleteBuildRecordError(f"build_index must be >= 1, got {bi}")

    artifact = str(rec["artifact_relpath"]).replace(chr(92), "/")
    # chr form for safety in this writer:
    return BuildRecord(
        build_index=bi,
        source_group_id=str(rec["source_group_id"]),
        source_sha256=str(rec["source_sha256"]).lower(),
        ex5_sha256=str(rec["ex5_sha256"]).lower(),
        experiment_id=str(rec["experiment_id"]),
        split=str(rec["split"]),
        label=str(rec["label"]),
        artifact_relpath=artifact,
        compiler_version=str(rec["compiler_version"]),
        family=rec.get("family") or rec.get("template_family"),
        template_family=rec.get("template_family") or rec.get("family"),
        optimize_setting=rec.get("optimize_setting"),
        staging_mq5=rec.get("staging_mq5"),
        evidence_ex5_abs=rec.get("evidence_ex5") or rec.get("evidence_ex5_abs"),
        ex5_size=rec.get("ex5_size"),
        compile_status=rec.get("compile_status"),
    )


def validate_build_records(records: Iterable[dict[str, Any]], *, project_root=None) -> list[BuildRecord]:
    return [normalize_build_record(dict(r), project_root=project_root) for r in records]


def select_by_build_index(records: Iterable[BuildRecord], build_index: int) -> list[BuildRecord]:
    return [r for r in records if r.build_index == build_index]


def infer_build_index_from_artifact(artifact_relpath: str) -> int | None:
    """Best-effort parse rN.ex5 filename using platform-independent path models."""
    name = historical_basename(artifact_relpath).lower()
    if name.startswith("r") and name.endswith(".ex5"):
        mid = name[1:-4]
        if mid.isdigit():
            return int(mid)
    return None
