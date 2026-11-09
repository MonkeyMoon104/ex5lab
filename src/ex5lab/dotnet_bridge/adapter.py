"""Optional subprocess bridge to ex5lab.BinaryResearch (.NET).

C# is optional. Python parser remains authoritative for the research framework.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from ex5lab.binary.ex5_header import parse_ex5_prefix
from ex5lab.binary.hashing import sha256_hex
from ex5lab.policy.static_only import assert_static_reconstruction_context

SCHEMA = "ex5lab.binaryresearch.v1"
DEFAULT_TIMEOUT_S = 30.0


class DotNetBridgeError(RuntimeError):
    """Raised when the optional .NET inspector cannot be used safely."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_dotnet_tool(*, root: Path | None = None) -> Path | None:
    """Locate built ex5lab.BinaryResearch executable if present."""
    root = root or _repo_root()
    candidates = [
        root
        / "tools/dotnet/ex5lab.BinaryResearch/bin/Release/net8.0/ex5lab.BinaryResearch.exe",
        root
        / "tools/dotnet/ex5lab.BinaryResearch/bin/Release/net8.0/ex5lab.BinaryResearch.dll",
        root
        / "tools/dotnet/ex5lab.BinaryResearch/bin/Debug/net8.0/ex5lab.BinaryResearch.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def inspect_ex5_python(path: Path) -> dict[str, Any]:
    """Python-side inspection contract aligned with the C# JSON schema (subset)."""
    assert_static_reconstruction_context(uses_strategy_tester=False)
    path = Path(path)
    data = path.read_bytes()
    digest = sha256_hex(data)
    prefix = parse_ex5_prefix(data)
    verified: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    if prefix.get("signature_ok"):
        verified.append(
            {
                "name": "signature",
                "offset": 0,
                "size": 3,
                "status": "VERIFIED_FORMAT_FIELD",
                "value": "EX5",
                "value_hex": data[:3].hex(),
            }
        )
    if prefix.get("kind_byte") is not None:
        candidates.append(
            {
                "name": "empirical_kind_byte",
                "offset": 3,
                "size": 1,
                "status": "EMPIRICAL_STRUCTURE",
                "value": prefix.get("kind_byte_hex"),
                "value_int": prefix.get("kind_byte"),
                "kind_class": prefix.get("kind_class"),
            }
        )
    if len(data) > 0x0B:
        candidates.append(
            {
                "name": "byte_0x0B",
                "offset": 0x0B,
                "size": 1,
                "status": "BINARY_CORRELATION_ONLY_UNPROVENANCED",
                "value_int": data[0x0B],
                "value_hex": f"{data[0x0B]:02x}",
            }
        )
    if len(data) >= 0x0E:
        le16 = int.from_bytes(data[0x0C:0x0E], "little")
        be16 = int.from_bytes(data[0x0C:0x0E], "big")
        candidates.append(
            {
                "name": "candidate_u16_at_0x0C",
                "offset": 0x0C,
                "size": 2,
                "status": "EMPIRICAL_PREFIX_FIELD_UNVALIDATED",
                "value_int": le16,
                "value_hex": data[0x0C:0x0E].hex(),
                "endianness": {"le16": le16, "be16": be16},
            }
        )
    ok = bool(prefix.get("ok"))
    return {
        "schema": SCHEMA,
        "ok": ok,
        "error": prefix.get("error"),
        "path": str(path.resolve()),
        "size_bytes": len(data),
        "sha256": digest,
        "signature_ok": prefix.get("signature_ok"),
        "prefix_hex": data[: min(32, len(data))].hex(),
        "executable_isa_declared": False,
        "decoder_available": False,
        "strategy_tester_used": False,
        "verified_fields": verified,
        "candidate_fields": candidates,
        "engine": "python",
    }


def inspect_ex5_dotnet(
    path: Path,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    tool: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Invoke the optional .NET inspector; validate schema and SHA-256."""
    assert_static_reconstruction_context(uses_strategy_tester=False)
    path = Path(path).resolve()
    if not path.is_file():
        raise DotNetBridgeError(f"missing EX5: {path}")

    tool = tool or resolve_dotnet_tool(root=root)
    if tool is None:
        raise DotNetBridgeError(
            "ex5lab.BinaryResearch executable not found. "
            "Build with: dotnet build tools/dotnet/ex5lab.BinaryResearch -c Release"
        )

    expected_sha = sha256_hex(path.read_bytes())
    cmd: list[str]
    if tool.suffix.lower() == ".dll":
        dotnet = shutil.which("dotnet")
        if not dotnet:
            raise DotNetBridgeError("dotnet host not on PATH")
        cmd = [dotnet, "exec", str(tool), str(path)]
    else:
        cmd = [str(tool), str(path)]

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env={**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise DotNetBridgeError(f"dotnet inspector timed out after {timeout_s}s") from exc
    elapsed = time.perf_counter() - t0

    if not proc.stdout.strip():
        raise DotNetBridgeError(
            f"empty stdout (exit={proc.returncode}): {proc.stderr.strip()[:400]}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DotNetBridgeError(f"invalid JSON from dotnet tool: {exc}") from exc

    if payload.get("schema") != SCHEMA:
        raise DotNetBridgeError(
            f"schema mismatch: got {payload.get('schema')!r}, expected {SCHEMA!r}"
        )
    reported = str(payload.get("sha256") or "").lower()
    if reported and reported != expected_sha:
        raise DotNetBridgeError(
            f"sha256 mismatch: tool={reported} local={expected_sha}"
        )

    payload["engine"] = "dotnet"
    payload["bridge"] = {
        "exit_code": proc.returncode,
        "elapsed_s": round(elapsed, 6),
        "tool": str(tool),
        "stderr": (proc.stderr or "").strip()[:1000] or None,
    }
    return payload


def compare_engines(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    """Compare Python and optional .NET inspection of the same file."""
    assert_static_reconstruction_context(uses_strategy_tester=False)
    py = inspect_ex5_python(path)
    out: dict[str, Any] = {"path": str(Path(path).resolve()), "python": py}
    try:
        dn = inspect_ex5_dotnet(path, root=root)
        out["dotnet"] = dn
        disagreements: list[str] = []
        for key in ("ok", "size_bytes", "sha256", "signature_ok", "prefix_hex"):
            if py.get(key) != dn.get(key):
                disagreements.append(f"{key}: python={py.get(key)!r} dotnet={dn.get(key)!r}")
        py_kind = _field(py, "empirical_kind_byte", "value_int")
        dn_kind = _field(dn, "empirical_kind_byte", "value_int")
        if py_kind != dn_kind:
            disagreements.append(f"kind_byte: python={py_kind!r} dotnet={dn_kind!r}")
        py_0b = _field(py, "byte_0x0B", "value_int")
        dn_0b = _field(dn, "byte_0x0B", "value_int")
        if py_0b != dn_0b:
            disagreements.append(f"byte_0x0B: python={py_0b!r} dotnet={dn_0b!r}")
        py_0c = _field(py, "candidate_u16_at_0x0C", "value_int")
        dn_0c = _field(dn, "candidate_u16_at_0x0C", "value_int")
        if py_0c != dn_0c:
            disagreements.append(f"u16@0x0C: python={py_0c!r} dotnet={dn_0c!r}")
        out["agreement"] = {
            "ok": not disagreements,
            "disagreements": disagreements,
        }
    except DotNetBridgeError as exc:
        out["dotnet"] = None
        out["dotnet_error"] = str(exc)
        out["agreement"] = {"ok": False, "disagreements": [f"dotnet_unavailable: {exc}"]}
    out["executable_isa_declared"] = False
    out["strategy_tester_used"] = False
    return out


def _field(payload: dict[str, Any], name: str, key: str) -> Any:
    for group in ("verified_fields", "candidate_fields"):
        for item in payload.get(group) or []:
            if item.get("name") == name:
                return item.get(key)
    return None
