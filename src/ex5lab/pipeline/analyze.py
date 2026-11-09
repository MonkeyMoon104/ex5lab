"""Generic authorized-EX5 analysis pipeline (no oracle/ dependency)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ex5lab.binary.hashing import sha256_hex
from ex5lab.blind.analyzer import BlindAnalysisError, analyze_ex5_blind


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "ex5"
    return stem[:80]


def _case_dir(output_root: Path, ex5: Path, sha: str) -> Path:
    return output_root / f"{_safe_stem(ex5.name)}_{sha[:12]}"


def _write_summary_md(report: dict[str, Any], path: Path) -> None:
    lines = [
        f"# EX5 analysis: {report.get('case_id')}",
        "",
        f"- SHA-256: `{report.get('sha256')}`",
        f"- Size: {report.get('size_bytes')} bytes",
        f"- EX5 magic: {report.get('header', {}).get('starts_with_ex5')}",
        f"- Offset-3: `{report.get('header', {}).get('byte3')}` ({report.get('header', {}).get('kind_hypothesis')})",
        f"- UTF-16LE strings: {', '.join(repr(s.get('value')) for s in report.get('utf16le_strings', [])) or '(none)'}",
        "",
        "## Reconstruction status",
        "",
        f"- `mq5_source_emitted`: **{report.get('reconstruction', {}).get('mq5_source_emitted')}**",
        f"- Reason: {report.get('reconstruction', {}).get('reason')}",
        "",
        "> This tool does **not** currently perform complete EX5?MQ5 decompilation.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def analyze_path(
    ex5_path: str | Path,
    output_root: str | Path,
    *,
    authorized_roots: list[Path] | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Analyze one EX5 into an isolated output case directory."""
    ex5_path = Path(ex5_path)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        report = analyze_ex5_blind(
            ex5_path,
            case_id=case_id or f"case_{_safe_stem(ex5_path.name)}",
            authorized_roots=authorized_roots,
        )
        errors: list[dict[str, Any]] = []
        ok = True
    except (BlindAnalysisError, OSError, ValueError) as exc:
        # Still allocate a directory using file hash if readable
        try:
            sha = sha256_hex(ex5_path.read_bytes()) if ex5_path.is_file() else "unreadable"
        except OSError:
            sha = "unreadable"
        out = _case_dir(output_root, ex5_path, sha if sha != "unreadable" else "000000000000")
        out.mkdir(parents=True, exist_ok=True)
        err = {"ok": False, "error": str(exc), "path": str(ex5_path)}
        (out / "errors.json").write_text(json.dumps(err, indent=2), encoding="utf-8")
        return err

    sha = report["sha256"]
    out = _case_dir(output_root, ex5_path, sha)
    out.mkdir(parents=True, exist_ok=True)

    analysis_path = out / "analysis.json"
    analysis_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_summary_md(report, out / "summary.md")

    freeze = {
        "case_id": report["case_id"],
        "ex5_path": str(ex5_path.resolve()),
        "ex5_sha256": sha,
        "ex5_size": report["size_bytes"],
        "blind_report_path": str(analysis_path.resolve()),
        "blind_report_sha256": sha256_hex(analysis_path.read_bytes()),
        "oracle_accessed": False,
        "mq5_fabricated": report.get("reconstruction", {}).get("mq5_source_emitted", False),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out / "freeze_manifest.json").write_text(json.dumps(freeze, indent=2), encoding="utf-8")

    provenance = {
        "tool": "ex5lab.pipeline.analyze",
        "phase": "3",
        "analyzer": "ex5lab.blind.analyzer",
        "input": str(ex5_path.resolve()),
        "output_dir": str(out.resolve()),
        "ex5_sha256": sha,
        "notes": [
            "Blind analysis only ? oracle/ was not read.",
            "No reconstructed.mq5 written because executable logic was not recovered.",
        ],
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (out / "errors.json").write_text(json.dumps({"ok": True, "errors": []}, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "case_id": report["case_id"],
        "output_dir": str(out),
        "ex5_sha256": sha,
        "freeze_manifest": str(out / "freeze_manifest.json"),
        "analysis": str(analysis_path),
    }


def analyze_batch(
    input_path: str | Path,
    output_root: str | Path,
    *,
    authorized_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """Analyze a single EX5 or all *.ex5 under a directory; continue after failures."""
    input_path = Path(input_path)
    output_root = Path(output_root)
    if input_path.is_file():
        files = [input_path]
        auth = authorized_roots or [input_path.parent]
    elif input_path.is_dir():
        files = sorted({p.resolve(): p for p in list(input_path.glob("*.ex5")) + list(input_path.glob("*.EX5"))}.values(), key=lambda x: x.name.lower())
        auth = authorized_roots or [input_path]
    else:
        return {"ok": False, "error": f"input not found: {input_path}", "results": []}

    results = []
    for f in files:
        results.append(analyze_path(f, output_root, authorized_roots=auth))
    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_n == len(results),
        "total": len(results),
        "succeeded": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
    }
