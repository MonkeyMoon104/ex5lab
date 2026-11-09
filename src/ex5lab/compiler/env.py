"""Official MetaEditor / MQL5 include discovery.

Only the stock MetaQuotes MetaTrader 5 install is considered. Broker-branded
terminals (for example Xlence) are ignored.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Official MetaQuotes install locations only.
CANDIDATE_METAEDITORS = [
    Path(r"C:\Program Files\MetaTrader 5\MetaEditor64.exe"),
    Path(r"C:\Program Files (x86)\MetaTrader 5\MetaEditor64.exe"),
]

_BROKER_ORIGIN_MARKERS = (
    "xlence",
)


def _read_origin_text(origin: Path) -> str:
    if not origin.is_file():
        return ""
    try:
        return origin.read_text(encoding="utf-16", errors="ignore")
    except OSError:
        return origin.read_text(encoding="utf-8", errors="ignore")


def _is_official_metatrader_origin(origin_txt: str) -> bool:
    lower = origin_txt.lower()
    if "metatrader 5" not in lower:
        return False
    return not any(marker in lower for marker in _BROKER_ORIGIN_MARKERS)


def discover_metaeditor(explicit: str | Path | None = None) -> dict[str, Any]:
    if explicit:
        p = Path(explicit)
        return {"path": str(p), "exists": p.is_file(), "source": "explicit"}
    env = os.environ.get("EX5LAB_METAEDITOR")
    if env:
        p = Path(env)
        return {"path": str(p), "exists": p.is_file(), "source": "env:EX5LAB_METAEDITOR"}
    for c in CANDIDATE_METAEDITORS:
        if c.is_file():
            return {"path": str(c), "exists": True, "source": "well_known_official"}
    return {"path": None, "exists": False, "source": "not_found"}


def discover_mql5_include(explicit: str | Path | None = None) -> dict[str, Any]:
    if explicit:
        p = Path(explicit)
        return {"path": str(p), "exists": p.is_dir(), "source": "explicit"}
    env = os.environ.get("EX5LAB_MQL5_INCLUDE")
    if env:
        p = Path(env)
        return {"path": str(p), "exists": p.is_dir(), "source": "env:EX5LAB_MQL5_INCLUDE"}
    appdata = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    if appdata.is_dir():
        for child in sorted(appdata.iterdir()):
            mql5 = child / "MQL5"
            if not mql5.is_dir():
                continue
            origin_txt = _read_origin_text(child / "origin.txt")
            if _is_official_metatrader_origin(origin_txt):
                return {
                    "path": str(mql5),
                    "exists": True,
                    "source": "appdata_official_metatrader5",
                    "terminal_id": child.name,
                }
    return {"path": None, "exists": False, "source": "not_found"}
