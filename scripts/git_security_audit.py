"""Read-only audit of paths that should not be committed (secrets, EX5, local dirs)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DENIED_NAME_PATTERNS = [
    r"\.env$",
    r"credentials.*\.json$",
    r"secrets\.json$",
    r"id_rsa$",
    r"id_ed25519$",
    r"\.pem$",
    r"\.ex5$",
    r"\.ex4$",
    r"EX5_DECOMPILER_SOURCE\.zip$",
]

DENIED_PATH_PREFIXES = (
    "input/",
    "oracle/",
    "output/",
    "reports/",
)


def classify(rel: str) -> str:
    norm = rel.replace("\\", "/")
    base = Path(norm).name
    for pat in DENIED_NAME_PATTERNS:
        if re.search(pat, base, flags=re.IGNORECASE):
            return "DENIED"
    lower = norm.lower()
    if any(lower.startswith(p) for p in DENIED_PATH_PREFIXES):
        # allow README/.gitkeep under input/oracle/reports
        if base.lower() in {".gitkeep", "readme.md"}:
            return "OK"
        return "DENIED"
    return "OK"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Read null-delimited paths from stdin (git diff --cached -z --name-only)",
    )
    args = parser.parse_args(argv)

    if args.staged:
        raw = sys.stdin.buffer.read().split(b"\0")
        paths = [p.decode("utf-8", errors="replace") for p in raw if p]
    else:
        paths = [
            str(p.relative_to(ROOT)).replace("\\", "/")
            for p in ROOT.rglob("*")
            if p.is_file()
        ]

    denied = []
    for rel in paths:
        if classify(rel) == "DENIED":
            denied.append(rel)

    if denied:
        print("DENIED paths:")
        for p in denied[:200]:
            print(f"  {p}")
        return 2
    print("OK: no denied paths in scan set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
