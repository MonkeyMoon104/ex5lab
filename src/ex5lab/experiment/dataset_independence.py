"""Source-template-family independence checks for research splits."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def normalize_mq5_source(text: str) -> str:
    """Normalize for structural comparison - not a full MQL5 parser."""
    # strip comments
    text = re.sub(r"//.*?$", "", text, flags=re.M)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # neutralize string literals
    text = re.sub(r'"[^"]*"', '""', text)
    # neutralize integer/float literals
    text = re.sub(r"\b\d+(?:\.\d+)?\b", "0", text)
    return text


def structural_fingerprint(text: str) -> str:
    norm = normalize_mq5_source(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def audit_phase5_families(root: Path) -> dict[str, Any]:
    man = json.loads((root / "corpus" / "phase5" / "CORPUS_MANIFEST.json").read_text(encoding="utf-8"))
    by_fp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_family: dict[str, list[str]] = defaultdict(list)
    rows = []
    for prog in man["programs"]:
        path = root / "corpus" / "phase5" / "sources" / prog["file"]
        text = path.read_text(encoding="utf-8", errors="replace")
        fp = structural_fingerprint(text)
        row = {
            "experiment_id": prog["experiment_id"],
            "family": prog.get("family"),
            "split": prog["split"],
            "label": prog["label"],
            "source_sha256": prog["source_sha256"],
            "structural_fingerprint": fp,
        }
        rows.append(row)
        by_fp[fp].append(row)
        by_family[prog.get("family") or "unknown"].append(prog["experiment_id"])

    collisions = {k: v for k, v in by_fp.items() if len(v) > 1}
    # split leakage: same structural fingerprint in train and holdout
    leakage = []
    for fp, members in collisions.items():
        splits = {m["split"] for m in members}
        if "train" in splits and "holdout" in splits:
            leakage.append({"fingerprint": fp, "members": members})

    return {
        "n_programs": len(rows),
        "n_declared_families": len(by_family),
        "n_unique_source_sha": len({r["source_sha256"] for r in rows}),
        "n_unique_structural_fingerprints": len(by_fp),
        "structural_collisions": [
            {"fingerprint": fp, "n": len(v), "ids": [m["experiment_id"] for m in v]}
            for fp, v in collisions.items()
        ],
        "train_holdout_structural_leakage": leakage,
        "independence_unit_recommendation": (
            "template_family+structural_fingerprint when collisions exist; "
            "else source_group_id remains minimum unit"
        ),
        "note": (
            "Different SHA-256 does not imply independent templates. "
            "Normalization is heuristic; Tree-sitter not required for this audit."
        ),
    }
