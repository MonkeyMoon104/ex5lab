"""Provenance helpers for reconstruction IR claims."""

from __future__ import annotations

from typing import Any

from ex5lab.reconstruction.ir import (
    EVIDENCE_STATUSES,
    EvidenceStatus,
    Provenance,
)


def make_provenance(
    *,
    method: str,
    evidence_status: EvidenceStatus = "UNKNOWN",
    ex5_sha256: str | None = None,
    binary_range: tuple[int, int] | None = None,
    experiment_id: str | None = None,
    notes: str = "",
) -> Provenance:
    if evidence_status not in EVIDENCE_STATUSES:
        raise ValueError(f"invalid evidence_status: {evidence_status}")
    return Provenance(
        method=method,
        evidence_status=evidence_status,
        ex5_sha256=ex5_sha256,
        binary_range=binary_range,
        experiment_id=experiment_id,
        notes=notes,
    )


def hypothetical(method: str = "synthetic_fixture", *, experiment_id: str | None = None) -> Provenance:
    return make_provenance(
        method=method,
        evidence_status="HYPOTHETICAL",
        experiment_id=experiment_id,
        notes="Synthetic / research IR; not binary-recovered.",
    )


def behavior_inferred(
    method: str,
    *,
    experiment_id: str | None = None,
    notes: str = "",
) -> Provenance:
    return make_provenance(
        method=method,
        evidence_status="BEHAVIOR_INFERRED",
        experiment_id=experiment_id,
        notes=notes or "Inferred from observable behavior under test vectors.",
    )


def source_assisted(
    method: str,
    *,
    experiment_id: str | None = None,
    notes: str = "",
) -> Provenance:
    return make_provenance(
        method=method,
        evidence_status="SOURCE_ASSISTED",
        experiment_id=experiment_id,
        notes=notes or "Constructed with knowledge of self-authored MQ5 source.",
    )


def binary_recovered(
    *,
    method: str,
    ex5_sha256: str,
    binary_range: tuple[int, int],
    experiment_id: str | None = None,
    notes: str = "",
) -> Provenance:
    """Only for claims backed by a documented byte range  -  still no opcode decode."""
    if binary_range[0] < 0 or binary_range[1] <= binary_range[0]:
        raise ValueError("binary_range must be [start, end) with end > start >= 0")
    if not ex5_sha256:
        raise ValueError("ex5_sha256 required for BINARY_RECOVERED")
    return make_provenance(
        method=method,
        evidence_status="BINARY_RECOVERED",
        ex5_sha256=ex5_sha256,
        binary_range=binary_range,
        experiment_id=experiment_id,
        notes=notes,
    )


def provenance_to_dict(p: Provenance) -> dict[str, Any]:
    return {
        "method": p.method,
        "evidence_status": p.evidence_status,
        "ex5_sha256": p.ex5_sha256,
        "binary_range": list(p.binary_range) if p.binary_range is not None else None,
        "experiment_id": p.experiment_id,
        "notes": p.notes,
    }


def claims_binary_recovery(p: Provenance) -> bool:
    return p.evidence_status == "BINARY_RECOVERED"
