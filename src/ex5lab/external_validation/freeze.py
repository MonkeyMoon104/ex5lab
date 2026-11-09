"""Candidate MQ5 freeze + immutability checks."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ex5lab.binary.hashing import sha256_hex
from ex5lab.external_validation.mql5_checks import (
    is_plausible_mql5_source,
    static_safety_review,
    syntax_shape_check,
)
from ex5lab.experiment.compile_util import sha256_file


class CandidateMutationError(RuntimeError):
    pass


def freeze_candidate(
    store_dir: Path,
    candidate_mq5: Path,
    *,
    converter_id: str | None = None,
) -> dict[str, Any]:
    """Copy candidate into store, hash, and write freeze manifest. Rejects empty paths."""
    if not candidate_mq5.is_file():
        raise FileNotFoundError(f"candidate MQ5 missing: {candidate_mq5}")
    store_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = store_dir / "candidate_frozen.mq5"
    if frozen_path.is_file():
        raise CandidateMutationError(
            "candidate already frozen; refusing silent replacement "
            f"(existing {frozen_path})"
        )
    data = candidate_mq5.read_bytes()
    digest = sha256_hex(data)
    frozen_path.write_bytes(data)
    text = frozen_path.read_text(encoding="utf-8", errors="replace")
    meta = {
        "schema": "external_validation_candidate_freeze_v1",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_path_recorded": str(candidate_mq5),
        "frozen_relpath": "candidate_frozen.mq5",
        "sha256": digest,
        "size_bytes": len(data),
        "converter_id": converter_id,
        "plausible_mql5": is_plausible_mql5_source(text),
        "static_safety": static_safety_review(text),
        "syntax_shape": syntax_shape_check(text),
        "immutable": True,
        "note": (
            "Ground truth must not be consulted until after this freeze. "
            "Replacing candidate_frozen.mq5 invalidates the challenge."
        ),
    }
    (store_dir / "candidate_freeze.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return meta


def verify_candidate_immutable(store_dir: Path) -> dict[str, Any]:
    """Fail if frozen bytes no longer match recorded SHA-256."""
    meta_path = store_dir / "candidate_freeze.json"
    frozen_path = store_dir / "candidate_frozen.mq5"
    if not meta_path.is_file() or not frozen_path.is_file():
        raise FileNotFoundError("missing freeze artifacts")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    current = sha256_file(frozen_path)
    expected = meta.get("sha256")
    ok = current == expected and frozen_path.stat().st_size == meta.get("size_bytes")
    if not ok:
        raise CandidateMutationError(
            f"frozen candidate mutated: expected {expected}, got {current}"
        )
    return {"ok": True, "sha256": current, "size_bytes": meta.get("size_bytes")}


def import_freeze_copy(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest
