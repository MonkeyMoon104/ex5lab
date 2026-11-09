"""Evidence classification helpers for research integrity."""

from __future__ import annotations

from enum import Enum
from typing import Any


class EvidenceClass(str, Enum):
    """How strongly a claim is supported."""

    VERIFIED_OBSERVATION = "verified_observation"
    OFFICIAL_DOCUMENTATION = "official_documentation"
    PLAUSIBLE_HYPOTHESIS = "plausible_hypothesis"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


def claim(
    statement: str,
    classification: EvidenceClass,
    *,
    evidence: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Return a structured, labeled research claim."""
    item: dict[str, Any] = {
        "statement": statement,
        "classification": classification.value,
    }
    if evidence is not None:
        item["evidence"] = evidence
    if notes is not None:
        item["notes"] = notes
    return item
