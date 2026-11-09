"""MetaEditor compilation-mode helpers .

Official modes (MetaEditor Help -> Compilation / Build menu):
  - Maximum Optimization
  - No Optimization

Project MQPROJ field: optimize "1" / "0" .
CLI MetaEditor64 /compile has no documented optimization switch  -  use .mqproj
or MetaEditor MCP compile_file(no_optimization=...).

Requested mode ≠ verified effective mode until cross-checked by artifact evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class CompileMode(str, Enum):
    MAXIMUM_OPTIMIZATION = "maximum_optimization"
    NO_OPTIMIZATION = "no_optimization"
    UNKNOWN = "unknown"


MODE_TO_MQPROJ_OPTIMIZE = {
    CompileMode.MAXIMUM_OPTIMIZATION: "1",
    CompileMode.NO_OPTIMIZATION: "0",
}

MQPROJ_OPTIMIZE_TO_MODE = {
    "1": CompileMode.MAXIMUM_OPTIMIZATION,
    "0": CompileMode.NO_OPTIMIZATION,
}


@dataclass(frozen=True)
class ModeRequest:
    requested: CompileMode
    mechanism: str  # mqproj_optimize | mcp_no_optimization | cli_default_unspecified
    mqproj_optimize: str | None = None
    mcp_no_optimization: bool | None = None


def classify_log_architecture(log_result_line: str | None) -> str | None:
    if not log_result_line:
        return None
    # e.g. cpu=\'X64 Regular\'
    if "cpu=" in log_result_line:
        try:
            return log_result_line.split("cpu=", 1)[1].strip().strip("'")
        except Exception:  # noqa: BLE001
            return None
    return None


def reconcile_compile_outcome(
    *,
    returncode: int | None,
    log_result_line: str | None,
    ex5_produced: bool,
    fresh_mtime_confirmed: bool,
) -> dict[str, Any]:
    """Preserve returncode, log, and artifact facts without silently normalizing."""
    zero_errors = bool(log_result_line and "0 errors" in log_result_line)
    artifact_ok = bool(ex5_produced and fresh_mtime_confirmed and zero_errors)
    return {
        "process_returncode": returncode,
        "log_result_line": log_result_line,
        "log_reports_zero_errors": zero_errors,
        "ex5_produced": ex5_produced,
        "fresh_mtime_confirmed": fresh_mtime_confirmed,
        "artifact_success": artifact_ok,
        "returncode_zero": returncode == 0,
        "contract_note": (
            "MetaEditor CLI frequently exits with returncode=1 even when the log "
            "reports 0 errors and a fresh EX5 was produced. Treat artifact+log as "
            "primary success criteria; do not rewrite returncode to 0."
        ),
        "status": (
            "verified_artifact_nonzero_exit"
            if artifact_ok and returncode not in (0, None)
            else ("verified" if artifact_ok and returncode == 0 else "failed_or_incomplete")
        ),
    }


def mode_verification_record(
    request: ModeRequest,
    *,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Assemble requested vs effective mode evidence."""
    return {
        "requested_mode": request.requested.value,
        "request_mechanism": request.mechanism,
        "mqproj_optimize_written": request.mqproj_optimize,
        "mcp_no_optimization": request.mcp_no_optimization,
        "effective_mode_claim": evidence.get("effective_mode_claim", CompileMode.UNKNOWN.value),
        "effective_mode_evidence": evidence.get("effective_mode_evidence", []),
        "effective_mode_confidence": evidence.get("effective_mode_confidence", "unverified"),
        "architecture_from_log": evidence.get("architecture_from_log"),
        "note": (
            "Effective mode is verified only when independent artifact evidence "
            "supports the request (e.g. systematic cross-mode binary differences "
            "beyond within-mode rebuild noise, or IDE/MCP confirmation)."
        ),
    }
