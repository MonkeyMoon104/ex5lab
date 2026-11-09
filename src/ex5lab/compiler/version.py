"""MetaEditor version provenance: expected vs observed vs verified."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def query_file_version_windows(exe: Path) -> dict[str, Any]:
    """Query FileVersion via PowerShell (Windows). Distinguishes observation methods."""
    exe = Path(exe)
    if not exe.is_file():
        return {
            "path": str(exe),
            "exists": False,
            "version_observed": None,
            "version_independently_verified": False,
            "method": "missing_file",
        }
    ps = (
        "$p = Get-Item -LiteralPath "
        + repr(str(exe))
        + "; $v = $p.VersionInfo.FileVersion; "
        "if (-not $v) { $v = $p.VersionInfo.ProductVersion }; "
        "Write-Output $v"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        ver = (proc.stdout or "").strip() or None
        return {
            "path": str(exe),
            "exists": True,
            "version_observed": ver,
            "version_independently_verified": bool(ver) and proc.returncode == 0,
            "method": "powershell_VersionInfo.FileVersion",
            "returncode": proc.returncode,
            "stderr": (proc.stderr or "")[:500],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "path": str(exe),
            "exists": True,
            "version_observed": None,
            "version_independently_verified": False,
            "method": "powershell_failed",
            "error": str(exc),
        }


def provenance_record(
    *,
    metaeditor: Path,
    version_expected: str | None = "5.0.0.6270",
) -> dict[str, Any]:
    obs = query_file_version_windows(metaeditor)
    return {
        "version_expected": version_expected,
        "version_observed": obs.get("version_observed"),
        "version_independently_verified": bool(obs.get("version_independently_verified")),
        "matches_expected": (
            obs.get("version_observed") == version_expected
            if obs.get("version_observed") and version_expected
            else None
        ),
        "observation": obs,
        "note": (
            "Hardcoded DEFAULT_VERSION strings are expectations only; "
            "they are not proof of the installed compiler version."
        ),
    }