"""Reproducible experiment manifest schema and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


REQUIRED_TOP_KEYS = {
    "schema_version",
    "phase",
    "experiment_id",
    "created_utc",
    "hypothesis",
    "classification_policy",
}


@dataclass
class ArtifactRef:
    path: str
    sha256: str
    size_bytes: int
    role: str  # source | ex5 | log | project | report


@dataclass
class BuildRecord:
    build_id: str
    source_path: str
    source_sha256: str
    ex5_path: str | None
    ex5_sha256: str | None
    ex5_size: int | None
    command: list[str]
    started_utc: str
    ended_utc: str
    log_result_line: str | None
    optimize_setting: str | None
    architecture: str | None
    metaeditor_version: str | None
    forced_recompile: bool
    notes: str = ""


@dataclass
class ExperimentManifest:
    schema_version: str
    phase: str
    experiment_id: str
    title: str
    hypothesis: str
    task: str  # A|B|C|E
    created_utc: str
    status: str  # planned|ran|blocked|verified
    settings: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    builds: list[dict[str, Any]] = field(default_factory=list)
    comparisons: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    classification_policy: str = (
        "Separate verified_observation / plausible_hypothesis / unknown / official_documentation"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def new(
        experiment_id: str,
        *,
        title: str,
        hypothesis: str,
        task: str,
        settings: dict[str, Any] | None = None,
    ) -> "ExperimentManifest":
        return ExperimentManifest(
            schema_version="1.0",
            phase="1",
            experiment_id=experiment_id,
            title=title,
            hypothesis=hypothesis,
            task=task,
            created_utc=datetime.now(timezone.utc).isoformat(),
            status="planned",
            settings=settings or {},
        )


def validate_manifest(data: dict[str, Any]) -> list[str]:
    """Return a list of validation errors (empty if valid)."""
    errors: list[str] = []
    for key in REQUIRED_TOP_KEYS:
        if key not in data:
            errors.append(f"missing required key: {key}")
    if "experiment_id" in data and not str(data["experiment_id"]).strip():
        errors.append("experiment_id must be non-empty")
    if "hypothesis" in data and not str(data["hypothesis"]).strip():
        errors.append("hypothesis must be non-empty")
    if "builds" in data and not isinstance(data["builds"], list):
        errors.append("builds must be a list")
    if "artifacts" in data and not isinstance(data["artifacts"], list):
        errors.append("artifacts must be a list")
    for i, art in enumerate(data.get("artifacts") or []):
        if not isinstance(art, dict):
            errors.append(f"artifacts[{i}] must be an object")
            continue
        for k in ("path", "sha256", "size_bytes", "role"):
            if k not in art:
                errors.append(f"artifacts[{i}] missing {k}")
        sha = art.get("sha256")
        if isinstance(sha, str) and len(sha) != 64:
            errors.append(f"artifacts[{i}].sha256 must be 64 hex chars")
    status = data.get("status")
    if status is not None and status not in {
        "planned",
        "ran",
        "blocked",
        "verified",
        "incomplete",
    }:
        errors.append(f"invalid status: {status}")
    return errors
