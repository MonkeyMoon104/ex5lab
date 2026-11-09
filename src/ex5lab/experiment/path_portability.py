"""Platform-independent interpretation of historical evidence paths."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath


class UnsafeEvidencePathError(ValueError):
    """Historical path cannot be safely mapped under the evidence root."""


_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def looks_like_windows_path(path_str: str) -> bool:
    s = str(path_str)
    if "\\" in s:
        return True
    if _DRIVE_RE.match(s):
        return True
    return False


def historical_basename(path_str: str) -> str:
    """Return filename using PureWindowsPath or PurePosixPath - not host Path."""
    s = str(path_str).strip()
    if not s:
        return ""
    if looks_like_windows_path(s):
        return PureWindowsPath(s).name
    if "/" in s:
        return PurePosixPath(s).name
    # bare filename
    return PurePosixPath(s.replace("\\", "/")).name


def historical_parts(path_str: str) -> tuple[str, ...]:
    s = str(path_str).strip()
    if not s:
        return ()
    if looks_like_windows_path(s):
        return PureWindowsPath(s).parts
    return PurePosixPath(s.replace("\\", "/")).parts


def extract_repo_relative_evidence_path(
    path_str: str,
    *,
    experiment_id: str | None = None,
    evidence_marker: str = "reports/phase5/ex5/",
) -> str | None:
    """Map a historical absolute/relative path to a portable repo-relative artifact.

    Historical Windows absolute paths are provenance hints only.
    Returns None if no safe mapping exists.
    """
    s = str(path_str).strip()
    if not s:
        return None

    # Normalize slashes for marker search without using host Path semantics
    normalized = s.replace("\\", "/")
    lower = normalized.lower()
    marker = evidence_marker.lower()
    idx = lower.find(marker)
    if idx >= 0:
        rel = normalized[idx:]
        # strip query-like junk
        rel = rel.split("?")[0]
        parts = PurePosixPath(rel).parts
        if ".." in parts or parts[:1] == ("/",):
            raise UnsafeEvidencePathError(f"path traversal in historical path: {path_str!r}")
        if not rel.startswith(evidence_marker) and not rel.lower().startswith(marker):
            # preserve original case from normalized slice starting at reports/
            # re-find with original normalized casing
            idx2 = normalized.lower().find(marker)
            rel = normalized[idx2:]
        # Force canonical marker prefix casing
        rest = rel[len(evidence_marker) :] if rel.lower().startswith(marker) else rel
        # If slice included marker with different case:
        if not rel.lower().startswith(marker):
            return None
        rest = normalized[idx + len(evidence_marker) :]
        cand = evidence_marker + rest
        parts = PurePosixPath(cand).parts
        if ".." in parts:
            raise UnsafeEvidencePathError(f"path traversal in historical path: {path_str!r}")
        return cand

    name = historical_basename(s).lower()
    bi = None
    if name.startswith("r") and name.endswith(".ex5"):
        mid = name[1:-4]
        if mid.isdigit():
            bi = int(mid)
    if bi is not None and experiment_id:
        eid = str(experiment_id)
        if "/" in eid or "\\" in eid or ".." in eid:
            raise UnsafeEvidencePathError(f"unsafe experiment_id: {experiment_id!r}")
        return f"{evidence_marker}{eid}/r{bi}.ex5"
    return None


def assert_under_evidence_root(rel: str, *, root: Path, allowed_prefix: str = "reports/phase5/ex5/") -> Path:
    """Resolve rel under root; reject escapes and absolute substitution."""
    root_r = root.resolve()
    rel_n = str(rel).replace("\\", "/").lstrip("/")
    if rel_n.startswith("..") or "/../" in f"/{rel_n}/":
        raise UnsafeEvidencePathError(f"traversal rejected: {rel}")
    if not rel_n.lower().startswith(allowed_prefix.lower()):
        raise UnsafeEvidencePathError(f"artifact outside evidence prefix: {rel}")
    candidate = (root_r / rel_n).resolve()
    try:
        candidate.relative_to(root_r)
    except ValueError as exc:
        raise UnsafeEvidencePathError(f"resolves outside project root: {rel}") from exc
    return candidate
