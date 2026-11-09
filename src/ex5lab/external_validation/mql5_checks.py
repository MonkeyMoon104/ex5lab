"""Lightweight static checks for untrusted MQ5 candidate text."""

from __future__ import annotations

import re
from typing import Any

UNSAFE_PATTERNS = [
    (r"#\s*import\b", "dll_import_directive"),
    (r"\bDLLImports\b", "dll_imports_block"),
    (r"\bShellExecute\b", "shell_execute"),
    (r"\bWinExec\b", "win_exec"),
    (r"\bCreateProcess\b", "create_process"),
    (r"\bURLDownloadToFile\b", "url_download"),
    (r"\bInternetOpen\b", "internet_open"),
    (r"\bWebRequest\b", "web_request"),
]

MQL5_HINTS = (
    "#property",
    "OnInit",
    "OnTick",
    "input ",
    "double ",
    "int ",
    "bool ",
)


def is_plausible_mql5_source(text: str) -> dict[str, Any]:
    """Heuristic: looks like MQL5 source, not proof of correctness."""
    hits = [h for h in MQL5_HINTS if h in text]
    return {
        "ok": len(hits) >= 2
        and ("OnInit" in text or "OnTick" in text or "#property" in text),
        "hint_hits": hits,
    }


def static_safety_review(text: str) -> dict[str, Any]:
    """Flag common dangerous patterns before anyone compiles a candidate."""
    findings = []
    for pat, label in UNSAFE_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            findings.append(label)
    return {
        "ok": not findings,
        "findings": findings,
        "status": "SAFE_FOR_COMPILE_CONSIDERATION" if not findings else "REJECT_UNSAFE",
    }


def syntax_shape_check(text: str) -> dict[str, Any]:
    """Brace/paren shape only  -  not a full MQL5 parser."""
    opens = text.count("{")
    closes = text.count("}")
    paren_ok = abs(text.count("(") - text.count(")")) <= 2
    return {
        "brace_balance_ok": opens == closes,
        "paren_near_balance": paren_ok,
        "has_function_like": bool(
            re.search(r"\b(int|double|bool|void)\s+\w+\s*\(", text)
        ),
        "ok": opens == closes and paren_ok,
    }
