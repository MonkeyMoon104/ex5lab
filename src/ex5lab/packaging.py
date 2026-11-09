"""Optional project ZIP packaging helpers (no test-suite dependency)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

CANONICAL_NAME = "EX5LAB_SOURCE.zip"
SIBLING_MANIFEST_NAME = "EX5LAB_SOURCE.manifest.json"

EXCLUDE_DIR_NAMES = {
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".idea",
    ".vscode",
    "compile_staging",
    ".ex5lab_zip_tmp",
    "bin",
    "obj",
    "input",
    "oracle",
    "output",
    "reports",
}

EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx", ".pml", ".ex5", ".ex4"}

EXCLUDE_FILE_NAMES = {
    CANONICAL_NAME,
    SIBLING_MANIFEST_NAME,
    ".env",
    ".env.local",
    "credentials.json",
    "secrets.json",
}

REQUIRED_PATH_PREFIXES = [
    "src/ex5lab/",
    "docs/",
    "pyproject.toml",
    "README.md",
]


def _is_excluded(rel: Path) -> bool:
    if rel.name in EXCLUDE_FILE_NAMES:
        return True
    if rel.name.startswith(CANONICAL_NAME + ".") or rel.name.startswith(CANONICAL_NAME + "_"):
        return True
    if rel.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if any(part in EXCLUDE_DIR_NAMES for part in rel.parts):
        return True
    if any(part.endswith(".egg-info") for part in rel.parts):
        return True
    return False


def iter_project_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if _is_excluded(rel):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_zip(root: Path, dest: Path) -> dict[str, Any]:
    files = iter_project_files(root)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(root).as_posix())
    return {"files": files, "count": len(files)}


def verify_zip(root: Path, zip_path: Path) -> list[str]:
    errors: list[str] = []
    if not zip_path.is_file():
        return ["zip does not exist"]
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                errors.append(f"CRC failure for member: {bad}")
            names = {n.replace("\\", "/") for n in zf.namelist()}
            if CANONICAL_NAME in names:
                errors.append("archive contains the ZIP itself")
            for banned in (".venv", "venv", "__pycache__", ".git", "input", "oracle"):
                if any(n == banned + "/" or n.startswith(banned + "/") for n in names):
                    errors.append(f"archive contains excluded dir: {banned}")
            for req in REQUIRED_PATH_PREFIXES:
                if req.endswith("/"):
                    if not any(n.startswith(req) for n in names):
                        errors.append(f"missing required prefix: {req}")
                elif req not in names:
                    errors.append(f"missing required file: {req}")
    except zipfile.BadZipFile as exc:
        errors.append(f"bad zip: {exc}")
    return errors


def write_sibling_manifest(package_result: dict[str, Any], *, root: Path | None = None) -> Path:
    root = (root or Path.cwd()).resolve()
    path = root / SIBLING_MANIFEST_NAME
    payload = {
        "schema_version": "4.0",
        "canonical_zip": package_result.get("filename") or CANONICAL_NAME,
        "absolute_path": package_result.get("canonical"),
        "size_bytes": package_result.get("size_bytes"),
        "sha256": package_result.get("sha256"),
        "file_count": package_result.get("file_count"),
        "verification_ok": bool(package_result.get("ok")),
        "verification_errors": package_result.get("errors") or [],
        "note": "Sibling manifest stays outside the ZIP.",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def package_project(root: Path | None = None) -> dict[str, Any]:
    root = (root or Path.cwd()).resolve()
    canonical = root / CANONICAL_NAME
    previous_valid = canonical.is_file()
    previous_sha = _sha256_file(canonical) if previous_valid else None
    tmp_dir = root / ".ex5lab_zip_tmp"
    try:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True)
        tmp_path = tmp_dir / CANONICAL_NAME
        built = build_zip(root, tmp_path)
        errors = verify_zip(root, tmp_path)
        if errors:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {
                "ok": False,
                "errors": errors,
                "canonical": str(canonical),
                "previous_preserved": previous_valid,
                "previous_sha256": previous_sha,
                "file_count_attempted": built["count"],
            }
        os.replace(tmp_path, canonical)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errors": [f"packaging exception: {exc}"],
            "canonical": str(canonical),
            "previous_preserved": previous_valid,
            "previous_sha256": previous_sha,
        }

    post_errors = verify_zip(root, canonical)
    sha = _sha256_file(canonical)
    size = canonical.stat().st_size
    with zipfile.ZipFile(canonical, "r") as zf:
        names = zf.namelist()
    return {
        "ok": not post_errors,
        "errors": post_errors,
        "canonical": str(canonical),
        "filename": CANONICAL_NAME,
        "size_bytes": size,
        "sha256": sha,
        "file_count": len(names),
        "previous_sha256": previous_sha,
        "replaced": True,
    }
