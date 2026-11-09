"""Freeze-manifest and evidence integrity checks (fail closed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ex5lab.binary.hashing import sha256_hex


class IntegrityError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_freeze_bundle(
    *,
    freeze_manifest_path: Path,
    blind_report_path: Path | None = None,
    expected_case_id: str | None = None,
    expected_ex5_path: Path | None = None,
) -> dict[str, Any]:
    """Verify freeze manifest integrity before scoring.

    Raises IntegrityError on failure (fail closed).
    """
    if not freeze_manifest_path.is_file():
        raise IntegrityError(f"freeze manifest missing: {freeze_manifest_path}")

    freeze = load_json(freeze_manifest_path)
    report_rel = freeze.get("blind_report_path")
    if blind_report_path is None:
        if not report_rel:
            raise IntegrityError("freeze missing blind_report_path")
        # resolve relative to freeze parent parents
        cand = freeze_manifest_path.parent / Path(report_rel).name
        if not cand.is_file():
            # try from project-ish relative
            cand = freeze_manifest_path.parent / Path(str(report_rel).replace("\\", "/")).name
        blind_report_path = cand if cand.is_file() else Path(report_rel)
    if not Path(blind_report_path).is_file():
        # also try beside freeze
        alt = freeze_manifest_path.parent / "analysis.json"
        alt2 = freeze_manifest_path.parent / "blind_report.json"
        if alt.is_file():
            blind_report_path = alt
        elif alt2.is_file():
            blind_report_path = alt2
        else:
            raise IntegrityError(f"blind report missing: {blind_report_path}")

    blind_report_path = Path(blind_report_path)
    recorded_report_sha = freeze.get("blind_report_sha256")
    live_report_sha = sha256_hex(blind_report_path.read_bytes())
    if not recorded_report_sha:
        raise IntegrityError("freeze missing blind_report_sha256")
    if recorded_report_sha != live_report_sha:
        raise IntegrityError(
            f"blind report SHA mismatch: freeze={recorded_report_sha} live={live_report_sha}"
        )

    blind = load_json(blind_report_path)
    case_id = freeze.get("case_id") or blind.get("case_id")
    if expected_case_id is not None and case_id != expected_case_id:
        raise IntegrityError(f"case_id mismatch: freeze={case_id} expected={expected_case_id}")

    ex5_sha_freeze = freeze.get("ex5_sha256")
    ex5_sha_blind = blind.get("sha256")
    if not ex5_sha_freeze or not ex5_sha_blind:
        raise IntegrityError("missing EX5 sha256 in freeze/blind report")
    if ex5_sha_freeze != ex5_sha_blind:
        raise IntegrityError(
            f"EX5 sha mismatch freeze vs blind report: {ex5_sha_freeze} != {ex5_sha_blind}"
        )

    # Path / file consistency
    ex5_path = Path(freeze.get("ex5_path") or blind.get("path") or "")
    if expected_ex5_path is not None:
        # compare by sha of expected file
        if not expected_ex5_path.is_file():
            raise IntegrityError(f"expected EX5 missing: {expected_ex5_path}")
        live = sha256_hex(expected_ex5_path.read_bytes())
        if live != ex5_sha_freeze:
            raise IntegrityError(
                f"selected input EX5 sha mismatch: expected_file={live} freeze={ex5_sha_freeze}"
            )
    elif ex5_path.is_file():
        live = sha256_hex(ex5_path.read_bytes())
        if live != ex5_sha_freeze:
            raise IntegrityError(
                f"EX5 path content mismatch: path={live} freeze={ex5_sha_freeze}"
            )

    return {
        "ok": True,
        "case_id": case_id,
        "blind_report_path": str(blind_report_path),
        "blind_report_sha256": live_report_sha,
        "ex5_sha256": ex5_sha_freeze,
        "freeze_manifest_path": str(freeze_manifest_path),
    }
