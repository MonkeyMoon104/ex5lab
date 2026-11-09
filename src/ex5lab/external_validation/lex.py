"""Narrow MQL5 lexical helpers for executable-code extraction.

Not a full MQL5 frontend. Distinguishes code vs line/block comments vs string
literals so structural comparison cannot treat commented text as executable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Kind = Literal["code", "line_comment", "block_comment", "string"]


@dataclass(frozen=True)
class Segment:
    kind: Kind
    text: str


def segment_mq5(text: str) -> list[Segment]:
    """Split source into code / comment / string segments (approximate lexer)."""
    out: list[Segment] = []
    i = 0
    n = len(text)
    buf: list[str] = []
    kind: Kind = "code"

    def flush(next_kind: Kind) -> None:
        nonlocal buf, kind
        if buf:
            out.append(Segment(kind, "".join(buf)))
            buf = []
        kind = next_kind

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if kind == "code":
            if ch == "/" and nxt == "/":
                flush("line_comment")
                buf.append("//")
                i += 2
                continue
            if ch == "/" and nxt == "*":
                flush("block_comment")
                buf.append("/*")
                i += 2
                continue
            if ch == '"':
                flush("string")
                buf.append('"')
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue

        if kind == "line_comment":
            buf.append(ch)
            i += 1
            if ch == "\n":
                flush("code")
            continue

        if kind == "block_comment":
            buf.append(ch)
            i += 1
            if ch == "*" and nxt == "/":
                buf.append("/")
                i += 1
                flush("code")
            continue

        # string
        buf.append(ch)
        i += 1
        if ch == "\\" and i < n:
            buf.append(text[i])
            i += 1
            continue
        if ch == '"':
            flush("code")

    flush("code")
    return [s for s in out if s.text]


def executable_code_only(text: str, *, blank_strings: bool = True) -> str:
    """Return text with comments removed; strings optionally blanked to \"\".

    Newlines inside removed block comments are preserved as spaces so line
    structure of surrounding code is not wildly shifted for brace matching.
    """
    parts: list[str] = []
    for seg in segment_mq5(text):
        if seg.kind == "code":
            parts.append(seg.text)
        elif seg.kind == "string":
            parts.append('""' if blank_strings else seg.text)
        elif seg.kind == "line_comment":
            parts.append("\n" if seg.text.endswith("\n") else "")
        else:
            # block comment -> keep newline count as whitespace
            parts.append("\n" * seg.text.count("\n"))
    return "".join(parts)
