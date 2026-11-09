"""Portable evidence path resolution relative to the repository root."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ex5lab.experiment.path_portability import (
    UnsafeEvidencePathError,
    assert_under_evidence_root,
    extract_repo_relative_evidence_path,
    historical_basename,
)


def project_root_from(here: Path | None = None) -> Path:
    if here is None:
        return Path(__file__).resolve().parents[3]
    return Path(here).resolve()


def to_repo_relative(path: Path | str, *, root: Path) -> str:
    """Best-effort portable relative path. Prefer extract_repo_relative_evidence_path for EX5 evidence."""
    s = str(path)
    extracted = extract_repo_relative_evidence_path(s)
    if extracted:
        return extracted
    p = Path(s)
    root = root.resolve()
    try:
        if p.is_absolute() and p.exists():
            return p.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        pass
    # Host Path.name is wrong for Windows paths on POSIX - use historical_basename
    return f"__external__/{historical_basename(s)}"


def resolve_evidence_path(
    artifact_relpath: str, *, root: Path, abs_hint: str | None = None
) -> Path:
    """Resolve evidence under the repository. Historical abs_hint is never an escape hatch."""
    root = root.resolve()
    rel = str(artifact_relpath).replace(chr(92), "/")
    if not rel or rel.startswith("__external__"):
        if abs_hint:
            extracted = extract_repo_relative_evidence_path(abs_hint)
            if extracted:
                rel = extracted
    candidate = assert_under_evidence_root(rel, root=root)
    if candidate.is_file():
        return candidate
    # Do NOT open abs_hint if it points outside the repo (cross-platform safety).
    if abs_hint:
        extracted = extract_repo_relative_evidence_path(abs_hint)
        if extracted:
            alt = assert_under_evidence_root(extracted, root=root)
            if alt.is_file():
                return alt
    raise FileNotFoundError(
        f"evidence artifact not found under repo: rel={rel} hint={abs_hint!r}"
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_artifact_sha(path: Path, expected_sha256: str) -> bool:
    return sha256_file(path).lower() == expected_sha256.lower()
