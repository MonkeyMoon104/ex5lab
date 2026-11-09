"""Label-neutral experiment identifiers and reused-holdout detection."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

# style label-derived staging/path prefixes (must not appear in Phase 5+ IDs).
LABEL_LEAK_PREFIXES = ("TP", "TA", "HP", "HA", "BP", "BA")
OPAQUE_ID_RE = re.compile(r"^x[0-9a-f]{8}$")


def make_opaque_experiment_id(seed_material: str, *, salt: str = "phase5") -> str:
    """Deterministic opaque id independent of semantic class encoding in the name."""
    digest = hashlib.sha256(f"{salt}:{seed_material}".encode("utf-8")).hexdigest()
    return f"x{digest[:8]}"


def is_opaque_experiment_id(eid: str) -> bool:
    return bool(OPAQUE_ID_RE.match(eid))


def has_label_derived_prefix(name: str) -> bool:
    stem = name.split(".")[0].upper()
    return any(stem.startswith(p) and len(stem) >= 4 and stem[2:4].isdigit() for p in LABEL_LEAK_PREFIXES)


def detect_source_sha_overlap(new_shas: Iterable[str], prior_shas: Iterable[str]) -> set[str]:
    """Return SHA-256 hashes present in both corpora (reused-source detection)."""
    prior = {s.lower() for s in prior_shas if s}
    return {s.lower() for s in new_shas if s and s.lower() in prior}
