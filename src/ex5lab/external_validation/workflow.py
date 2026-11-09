"""Three-stage external validation challenge store."""

from __future__ import annotations

import json
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ex5lab.binary.hashing import sha256_hex
from ex5lab.decoder.availability import DECODER_AVAILABLE
from ex5lab.experiment.compile_util import sha256_file
from ex5lab.policy.static_only import assert_static_reconstruction_context

_CHALLENGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class InvalidChallengeIdError(ValueError):
    """Challenge identifier escapes the store root or uses illegal characters."""


def validate_challenge_id(challenge_id: str) -> str:
    """Reject absolute paths, separators, traversal, and empty/invalid IDs."""
    if not isinstance(challenge_id, str) or not challenge_id.strip():
        raise InvalidChallengeIdError("challenge_id must be a non-empty string")
    cid = challenge_id.strip()
    if cid in {".", ".."}:
        raise InvalidChallengeIdError("challenge_id must not be '.' or '..'")
    if any(sep in cid for sep in ("/", "\\", "\0")):
        raise InvalidChallengeIdError("challenge_id must not contain path separators")
    if ".." in cid:
        raise InvalidChallengeIdError("challenge_id must not contain '..'")
    if Path(cid).is_absolute():
        raise InvalidChallengeIdError("challenge_id must not be an absolute path")
    if not _CHALLENGE_ID_RE.fullmatch(cid):
        raise InvalidChallengeIdError(
            "challenge_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}"
        )
    return cid


class ChallengeStore:
    """Filesystem layout for one external-validation challenge."""

    def __init__(self, root: Path, challenge_id: str):
        self.root = Path(root).resolve()
        self.challenge_id = validate_challenge_id(challenge_id)
        self.dir = (self.root / self.challenge_id).resolve()
        try:
            self.dir.relative_to(self.root)
        except ValueError as exc:
            raise InvalidChallengeIdError(
                f"challenge path escapes store root: {self.dir}"
            ) from exc

    @property
    def manifest_path(self) -> Path:
        return self.dir / "challenge_manifest.json"

    @property
    def ex5_path(self) -> Path:
        return self.dir / "subject.ex5"

    @property
    def ground_truth_vault(self) -> Path:
        return self.dir / "ground_truth_vault"

    @property
    def ground_truth_path(self) -> Path:
        return self.ground_truth_vault / "original.mq5"

    @property
    def unlock_path(self) -> Path:
        return self.dir / "GROUND_TRUTH_UNLOCKED.json"


def prepare_challenge(
    store_root: Path,
    ex5_path: Path,
    *,
    challenge_id: str | None = None,
    compiler_provenance: dict[str, Any] | None = None,
    protocol_notes: str | None = None,
    synthetic: bool = True,
    seal_ground_truth_mq5: Path | None = None,
) -> dict[str, Any]:
    """Stage 1: register EX5 (+ optional sealed vault of ground truth, locked)."""
    assert_static_reconstruction_context(uses_strategy_tester=False)
    if not ex5_path.is_file():
        raise FileNotFoundError(ex5_path)
    cid = validate_challenge_id(challenge_id) if challenge_id else ("syn_" + secrets.token_hex(4))
    store = ChallengeStore(store_root, cid)
    if store.dir.exists():
        raise FileExistsError(f"challenge already exists: {store.dir}")
    store.dir.mkdir(parents=True)
    data = ex5_path.read_bytes()
    store.ex5_path.write_bytes(data)
    gt_meta = None
    if seal_ground_truth_mq5 is not None:
        if not seal_ground_truth_mq5.is_file():
            raise FileNotFoundError(seal_ground_truth_mq5)
        store.ground_truth_vault.mkdir(parents=True)
        gt_bytes = seal_ground_truth_mq5.read_bytes()
        store.ground_truth_path.write_bytes(gt_bytes)
        # Keep vault "locked" until unlock_ground_truth writes unlock marker.
        gt_meta = {
            "sealed": True,
            "unlocked": False,
            "sha256": sha256_hex(gt_bytes),
            "size_bytes": len(gt_bytes),
            "relpath": "ground_truth_vault/original.mq5",
            "contamination_risk": (
                "Ground truth bytes exist on the same machine as the challenge store. "
                "This is NOT a cryptographically sealed independent lab. "
                "Do not claim true blind independence unless isolation is enforced operationally."
            ),
        }
        (store.ground_truth_vault / "SEALED.txt").write_text(
            "LOCKED until Stage 3 unlock. Do not read during Stage 2 freeze.\n",
            encoding="utf-8",
        )

    manifest = {
        "schema": "external_validation_challenge_v1",
        "challenge_id": cid,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic_fixture": synthetic,
        "ex5": {
            "relpath": "subject.ex5",
            "sha256": sha256_hex(data),
            "size_bytes": len(data),
            "source_path_recorded": str(ex5_path),
        },
        "compiler_provenance": compiler_provenance or {},
        "protocol": {
            "stage1": "prepare",
            "stage2": "freeze_candidate_before_unlocking_ground_truth",
            "stage3": "unlock_and_evaluate",
            "notes": protocol_notes
            or (
                "Provide only subject.ex5 to an external converter. "
                "Import returned MQ5 via freeze. Unlock ground truth only afterward."
            ),
        },
        "ground_truth": gt_meta,
        "ex5lab_decoder_available": DECODER_AVAILABLE,
        "candidate_frozen": False,
        "evaluation_complete": False,
    }
    store.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def unlock_ground_truth(store: ChallengeStore) -> dict[str, Any]:
    """Stage 3 gate: mark vault readable for evaluation (local trust model)."""
    if not store.ground_truth_path.is_file():
        raise FileNotFoundError("no sealed ground truth in this challenge")
    if not (store.dir / "candidate_freeze.json").is_file():
        raise RuntimeError("refuse unlock: candidate not frozen (Stage 2 required first)")
    meta = {
        "unlocked_at_utc": datetime.now(timezone.utc).isoformat(),
        "ground_truth_sha256": sha256_file(store.ground_truth_path),
        "warning": (
            "Unlock is a local policy marker, not cryptographic isolation from the operator."
        ),
    }
    store.unlock_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    man = json.loads(store.manifest_path.read_text(encoding="utf-8"))
    if man.get("ground_truth"):
        man["ground_truth"]["unlocked"] = True
    store.manifest_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return meta


def load_manifest(store: ChallengeStore) -> dict[str, Any]:
    return json.loads(store.manifest_path.read_text(encoding="utf-8"))


def attach_report(store: ChallengeStore, report: dict[str, Any]) -> Path:
    path = store.dir / "evaluation_report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    man = load_manifest(store)
    man["evaluation_complete"] = True
    man["candidate_frozen"] = (store.dir / "candidate_freeze.json").is_file()
    store.manifest_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return path


def attach_director_l4_certification(
    store: ChallengeStore, certification: dict[str, Any]
) -> dict[str, Any]:
    """Store reviewer-approved L4 certification on the challenge manifest.

    Does not by itself award L4  -  ``evaluate_frozen_challenge`` must re-run with
    this record present and provenance checks must pass.
    """
    man = load_manifest(store)
    man["director_l4_certification"] = certification
    store.manifest_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return certification


def copy_provider_facing_ex5(store: ChallengeStore, dest: Path) -> Path:
    """Copy only the EX5 for provider handoff  -  never ground truth."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(store.ex5_path, dest)
    return dest
