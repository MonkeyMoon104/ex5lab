#!/usr/bin/env python3
"""Audit local research environment for Phase 0."""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _file_version_windows(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buf):
            return None
        u = ctypes.c_void_p()
        ulen = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(
            buf, "\\", ctypes.byref(u), ctypes.byref(ulen)
        ):
            return None

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", wintypes.DWORD),
                ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD),
                ("dwFileVersionLS", wintypes.DWORD),
                ("dwProductVersionMS", wintypes.DWORD),
                ("dwProductVersionLS", wintypes.DWORD),
                ("dwFileFlagsMask", wintypes.DWORD),
                ("dwFileFlags", wintypes.DWORD),
                ("dwFileOS", wintypes.DWORD),
                ("dwFileType", wintypes.DWORD),
                ("dwFileSubtype", wintypes.DWORD),
                ("dwFileDateMS", wintypes.DWORD),
                ("dwFileDateLS", wintypes.DWORD),
            ]

        info = ctypes.cast(u, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        ms, ls = info.dwFileVersionMS, info.dwFileVersionLS
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return None


def find_metaeditor() -> dict:
    # Official MetaQuotes MetaTrader 5 / MetaEditor only (no broker rebrands).
    candidates = [
        Path(r"C:\Program Files\MetaTrader 5\MetaEditor64.exe"),
        Path(r"C:\Program Files (x86)\MetaTrader 5\MetaEditor64.exe"),
    ]
    found = []
    for c in candidates:
        if c.is_file():
            found.append(
                {
                    "path": str(c),
                    "size_bytes": c.stat().st_size,
                    "file_version": _file_version_windows(c),
                }
            )
    return {"candidates_checked": [str(c) for c in candidates], "found": found}


def find_terminal_data() -> list[dict]:
    base = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    results = []
    if not base.is_dir():
        return results
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name in {"Common", "Community", "Help"}:
            continue
        origin = child / "origin.txt"
        mql5 = child / "MQL5"
        entry = {
            "id": child.name,
            "path": str(child),
            "has_mql5": mql5.is_dir(),
            "origin": origin.read_text(encoding="utf-16", errors="ignore").strip()
            if origin.is_file()
            else None,
        }
        # origin.txt is often UTF-16 LE on Windows MetaQuotes installs
        if origin.is_file() and not entry["origin"]:
            entry["origin"] = origin.read_text(encoding="utf-8", errors="ignore").strip()
        results.append(entry)
    return results


def main() -> int:
    report = {
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "version_info": list(sys.version_info[:3]),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "project_root": str(ROOT),
        "metaeditor": find_metaeditor(),
        "terminal_data_folders": find_terminal_data(),
    }
    out = ROOT / "reports" / "env_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
