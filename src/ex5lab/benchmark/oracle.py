"""Parse ground-truth metadata from actual MQ5 sources ? never from EX5-derived manifests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_PROP_RE = re.compile(
    r'#property\s+(copyright|version|description|strict|script_show_inputs|indicator_chart_window|'
    r'indicator_separate_window|service|library)\s*(?:"([^"]*)")?',
    re.IGNORECASE,
)
_INCLUDE_RE = re.compile(r'#include\s*[<"]([^>"]+)[>"]')


def parse_mq5_properties(source_text: str) -> dict[str, Any]:
    props: dict[str, Any] = {
        "copyright": None,
        "version": None,
        "description": None,
        "flags": [],
    }
    for m in _PROP_RE.finditer(source_text):
        key = m.group(1).lower()
        val = m.group(2)
        if key in {"copyright", "version", "description"}:
            props[key] = val if val is not None else ""
        else:
            props["flags"].append(key)
    return props


def infer_program_kind_from_source(source_text: str, path: Path | None = None) -> str:
    props = parse_mq5_properties(source_text)
    flags = set(props["flags"])
    if "service" in flags:
        return "service"
    if "library" in flags:
        return "library"
    if "indicator_chart_window" in flags or "indicator_separate_window" in flags:
        return "indicator"
    # Heuristic: OnCalculate => indicator; OnTick+OnInit without OnStart alone => EA
    has_onstart = "void OnStart" in source_text or "int OnStart" in source_text
    has_ontick = "void OnTick" in source_text
    has_oncalc = "OnCalculate" in source_text
    if has_oncalc:
        return "indicator"
    if has_ontick or ("OnInit" in source_text and not has_onstart):
        return "expert"
    if has_onstart:
        return "script"
    if path and path.suffix.lower() == ".mq5":
        return "unknown_mq5"
    return "unknown"


def collect_includes(entry: Path, include_roots: list[Path]) -> dict[str, Any]:
    """Transitive #include closure relative to include_roots."""
    seen: set[str] = set()
    missing: list[str] = []
    external: list[str] = []
    order: list[str] = []

    def resolve(rel: str, current: Path) -> Path | None:
        # angle includes typically under Include/
        candidates = []
        if current.parent:
            candidates.append(current.parent / rel.replace("\\", "/"))
        for root in include_roots:
            candidates.append(root / rel.replace("\\", "/"))
            candidates.append(root / "Include" / rel.replace("\\", "/"))
        for c in candidates:
            if c.is_file():
                return c.resolve()
        return None

    def walk(path: Path) -> None:
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        order.append(key)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            missing.append(str(path))
            return
        for m in _INCLUDE_RE.finditer(text):
            rel = m.group(1)
            resolved = resolve(rel, path)
            if resolved is None:
                # Treat standard library includes as external if under system MQL5 later
                missing.append(rel)
                external.append(rel)
            else:
                walk(resolved)

    walk(entry.resolve())
    return {
        "entry": str(entry.resolve()),
        "closure_files": order,
        "closure_count": len(order),
        "missing_or_unresolved": sorted(set(missing)),
        "unresolved_count": len(set(missing)),
        "external_candidates": sorted(set(external)),
    }


def load_source_oracle(oracle_dir: Path, entry_name: str | None = None) -> dict[str, Any]:
    """Load oracle from oracle/. Returns status ORACLE_MISSING if entry absent."""
    oracle_dir = Path(oracle_dir)
    if not oracle_dir.is_dir():
        return {"status": "ORACLE_MISSING", "reason": f"oracle dir missing: {oracle_dir}"}

    entry = None
    if entry_name:
        cand = oracle_dir / entry_name
        if cand.is_file():
            entry = cand
    if entry is None:
        mq5s = sorted(oracle_dir.glob("*.mq5"))
        if not mq5s:
            return {"status": "ORACLE_MISSING", "reason": "no .mq5 entry in oracle/"}
        entry = mq5s[0]

    text = entry.read_text(encoding="utf-8", errors="replace")
    props = parse_mq5_properties(text)
    kind = infer_program_kind_from_source(text, entry)
    include_root = oracle_dir / "Include"
    roots = [oracle_dir]
    if include_root.is_dir():
        roots.append(include_root)
    closure = collect_includes(entry, roots)

    # Internal closure: files under oracle/
    internal = [p for p in closure["closure_files"] if str(oracle_dir.resolve()) in p]
    # Missing that look like project includes vs stdlib
    stdlib_prefixes = ("Trade/", "Object.mqh", "StdLib", "Controls/", "ChartObjects/", "Files/", "Arrays/")
    project_missing = []
    stdlib_missing = []
    for rel in closure["missing_or_unresolved"]:
        if any(rel.startswith(p) or p in rel for p in stdlib_prefixes):
            stdlib_missing.append(rel)
        else:
            project_missing.append(rel)

    return {
        "status": "ORACLE_PRESENT",
        "entry_path": str(entry),
        "entry_name": entry.name,
        "properties": props,
        "program_kind": kind,
        "include_closure": closure,
        "internal_include_count": len(internal),
        "project_includes_missing": project_missing,
        "stdlib_or_external_missing": stdlib_missing,
        "internal_include_closure_complete": len(project_missing) == 0,
        "source_text_sha_note": "properties parsed from actual MQ5 text, not EX5-derived manifest",
    }
