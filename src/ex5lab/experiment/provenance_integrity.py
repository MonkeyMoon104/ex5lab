"""Compile-log / experiment provenance integrity (fail closed)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_log_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-16-le", "utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_cpu_and_opt(log_text: str) -> dict[str, Any]:
    result = None
    for line in log_text.splitlines():
        if "elapsed" in line.lower() and ("cpu=" in line or "result:" in line.lower()):
            result = line.strip()
    cpu = None
    if result and "cpu=" in result:
        cpu = result.split("cpu=", 1)[1].strip().strip("'")
    return {
        "result_line": result,
        "architecture_from_log": cpu,
        "without_optimizations": bool(result and "without optimizations" in result),
    }


def verify_log_label_consistency(
    log_path: Path,
    *,
    claimed_architecture: str | None,
    claimed_no_optimization: bool | None = None,
) -> dict[str, Any]:
    """Fail closed when an on-disk MetaEditor log contradicts experiment labels."""
    if not log_path.is_file():
        return {
            "ok": False,
            "status": "LOG_MISSING",
            "errors": [f"missing log: {log_path}"],
        }
    text = read_log_text(log_path)
    parsed = parse_cpu_and_opt(text)
    errors: list[str] = []
    if claimed_architecture and parsed["architecture_from_log"]:
        # Normalize loose matching: AVX2 + FMA3 vs AVX2
        claimed_n = claimed_architecture.lower().replace(" ", "")
        actual_n = parsed["architecture_from_log"].lower().replace(" ", "")
        if claimed_n not in actual_n and actual_n not in claimed_n:
            errors.append(
                f"architecture mismatch: claimed={claimed_architecture!r} "
                f"log={parsed['architecture_from_log']!r}"
            )
    if claimed_no_optimization is True and not parsed["without_optimizations"]:
        errors.append("claimed no-optimization but log lacks 'without optimizations'")
    if claimed_no_optimization is False and parsed["without_optimizations"]:
        errors.append("claimed optimized build but log reports without optimizations")
    return {
        "ok": not errors,
        "status": "LOG_LABEL_OK" if not errors else "LOG_LABEL_CONTRADICTION",
        "log_sha256": sha256_file(log_path),
        "parsed": parsed,
        "errors": errors,
    }


def audit_identical_logs(log_dir: Path) -> dict[str, Any]:
    files = sorted(log_dir.glob("*.log"))
    by_hash: dict[str, list[str]] = {}
    for p in files:
        by_hash.setdefault(sha256_file(p), []).append(p.name)
    dupes = {h: names for h, names in by_hash.items() if len(names) > 1}
    return {
        "file_count": len(files),
        "unique_hashes": len(by_hash),
        "duplicate_groups": dupes,
        "all_identical": len(by_hash) == 1 and len(files) > 1,
        "status": (
            "PROVENANCE_DEFECT_IDENTICAL_LOGS"
            if len(by_hash) == 1 and len(files) > 1
            else "LOG_HASHES_OK"
        ),
    }