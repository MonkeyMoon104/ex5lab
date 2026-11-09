"""MetaEditor compilation helpers for controlled experiments."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_METAEDITOR = Path(r"C:\Program Files\MetaTrader 5\MetaEditor64.exe")
DEFAULT_INCLUDE = Path(
    os.environ.get("EX5LAB_MQL5_INCLUDE")
    or str(Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal")
)
DEFAULT_VERSION = "5.0.0.6270"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_log_text(path: Path) -> str:
    if not path.is_file():
        return ""
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-16-le", "utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_result_line(log_text: str) -> str | None:
    result = None
    for line in log_text.splitlines():
        if "result:" in line.lower():
            result = line.strip()
    return result


def make_mqproj(
    project_path: Path,
    mq5_name: str,
    *,
    program_type: str,
    optimize: str,
    fpzerocheck: str = "1",
    copyright: str = "ex5lab research",
    version: str = "1.00",
) -> Path:
    """Write a MetaEditor-style project file with explicit optimize setting.

    MetaEditor's project JSON treats backslash escapes (e.g. \0) specially, so
    paths must contain an escaped backslash (two backslash characters in file).
    Projects should be compiled from inside a terminal MQL5 tree.
    """
    project_path.parent.mkdir(parents=True, exist_ok=True)
    # Emit .\\filename so parser sees escaped '\' + filename (not \0 octal/escape).
    path_value = ".\\\\" + mq5_name  # file bytes: . \ \ name
    body = "\n".join(
        [
            "{",
            '  "platform"    :"mt5",',
            f'  "program_type":"{program_type}",',
            f'  "copyright"   :"{copyright}",',
            '  "link"        :"",',
            f'  "version"     :"{version}",',
            f'  "optimize"    :"{optimize}",',
            f'  "fpzerocheck" :"{fpzerocheck}",',
            '  "tester_no_cache":"0",',
            '  "tester_everytick_calculate":"0",',
            '  "unicode_character_set":"0",',
            '  "static_libraries":"0",',
            "",
            '  "files":',
            "  [",
            "    {",
            f'      "path":"{path_value}",',
            '      "compile":"true",',
            '      "relative_to_project":"true"',
            "    }",
            "  ]",
            "}",
            "",
        ]
    )
    project_path.write_text(body, encoding="utf-8", newline="\n")
    return project_path

def compile_target(
    target: Path,
    *,
    out_ex5: Path,
    metaeditor: Path = DEFAULT_METAEDITOR,
    include: Path = DEFAULT_INCLUDE,
    timeout_s: int = 120,
    optimize_setting: str | None = None,
    architecture_expected: str = "X64 Regular",
) -> dict[str, Any]:
    """Compile an .mq5 or .mqproj, forcing fresh EX5 generation.

    Copies the produced EX5 next to `out_ex5`. Deletes any pre-existing EX5 beside
    the compile target before invoking MetaEditor to avoid silent reuse.
    """
    target = target.resolve()
    work_dir = target.parent
    if target.suffix.lower() == ".mqproj":
        # EX5 name follows the primary mq5 file listed in project; we detect newly written .ex5
        preexisting = {p.resolve() for p in work_dir.glob("*.ex5")}
        for p in list(preexisting):
            p.unlink(missing_ok=True)
        for p in work_dir.glob("*.log"):
            p.unlink(missing_ok=True)
        compile_arg = str(target)
    else:
        staged_ex5 = target.with_suffix(".ex5")
        staged_log = target.with_suffix(".log")
        staged_ex5.unlink(missing_ok=True)
        staged_log.unlink(missing_ok=True)
        preexisting = set()
        compile_arg = str(target)

    cmd = [
        str(metaeditor),
        f"/compile:{compile_arg}",
        f"/include:{include}",
        "/log",
    ]
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    mtime_guard = time.time()
    # Small sleep so filesystem mtimes cannot match a pre-deleted phantom.
    time.sleep(0.05)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, check=False
        )
        timed_out = False
        returncode = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = (
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
    elapsed = time.perf_counter() - t0
    ended = datetime.now(timezone.utc)

    # Find produced EX5: prefer same-stem for mq5; else newest ex5 in folder newer than guard.
    produced: Path | None = None
    if target.suffix.lower() == ".mq5":
        candidate = target.with_suffix(".ex5")
        if candidate.is_file():
            produced = candidate
    if produced is None:
        candidates = sorted(
            work_dir.glob("*.ex5"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for c in candidates:
            if c.stat().st_mtime + 0.01 >= mtime_guard:
                produced = c
                break

    log_path = None
    log_text = ""
    if target.suffix.lower() == ".mq5":
        lp = target.with_suffix(".log")
        if lp.is_file():
            log_path = lp
            log_text = read_log_text(lp)
    else:
        logs = sorted(work_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if logs:
            log_path = logs[0]
            log_text = read_log_text(log_path)

    result_line = parse_result_line(log_text)
    fresh = False
    if produced and produced.is_file():
        fresh = produced.stat().st_mtime + 0.01 >= mtime_guard
        out_ex5.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(produced, out_ex5)
        if log_path and log_path.is_file():
            shutil.copy2(log_path, out_ex5.with_suffix(".log"))

    from ex5lab.compiler.modes import classify_log_architecture, reconcile_compile_outcome

    produced_ok = bool(produced and produced.is_file())
    zero_errors = bool(result_line and "0 errors" in result_line)
    # Artifact+log success; do NOT require returncode==0 (MetaEditor CLI often exits 1).
    artifact_verified = bool(out_ex5.is_file() and fresh and zero_errors)
    reconciliation = reconcile_compile_outcome(
        returncode=returncode,
        log_result_line=result_line,
        ex5_produced=produced_ok and out_ex5.is_file(),
        fresh_mtime_confirmed=fresh,
    )
    record = {
        "target": str(target),
        "command": cmd,
        "started_utc": started.isoformat(),
        "ended_utc": ended.isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "timed_out": timed_out,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "log_path": str(log_path) if log_path else None,
        "log_result_line": result_line,
        "architecture_from_log": classify_log_architecture(result_line),
        "ex5_produced": produced_ok and out_ex5.is_file(),
        "forced_recompile": True,
        "fresh_mtime_confirmed": fresh,
        "optimize_setting": optimize_setting,
        "architecture_expected": architecture_expected,
        "metaeditor": str(metaeditor),
        "metaeditor_version": DEFAULT_VERSION,
        "include": str(include),
        "output_ex5": str(out_ex5) if out_ex5.is_file() else None,
        "ex5_sha256": sha256_file(out_ex5) if out_ex5.is_file() else None,
        "ex5_size": out_ex5.stat().st_size if out_ex5.is_file() else None,
        "compiler_result_reconciliation": reconciliation,
        "status": (
            "verified"
            if artifact_verified
            else ("ran_no_ex5" if not out_ex5.is_file() else "ran")
        ),
    }
    return record
