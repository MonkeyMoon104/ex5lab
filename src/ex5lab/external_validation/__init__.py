"""Black-box validation helpers for third-party EX5-to-MQ5 claims.

Compares a frozen candidate MQ5 to unlocked ground truth you supply.
Does not activate ex5lab binary decoder (`DECODER_AVAILABLE` stays False).
"""

from __future__ import annotations

from ex5lab.external_validation.evaluate import evaluate_frozen_challenge
from ex5lab.external_validation.freeze import freeze_candidate, verify_candidate_immutable
from ex5lab.external_validation.levels import ValidationLevel, achieved_levels
from ex5lab.external_validation.mechanisms import MechanismHypothesis, classify_claim_set
from ex5lab.external_validation.provenance import (
    validate_compile_provenance,
    validate_l4_certification,
)
from ex5lab.external_validation.workflow import (
    ChallengeStore,
    InvalidChallengeIdError,
    attach_director_l4_certification,
    prepare_challenge,
    unlock_ground_truth,
    validate_challenge_id,
)

__all__ = [
    "ChallengeStore",
    "InvalidChallengeIdError",
    "MechanismHypothesis",
    "ValidationLevel",
    "achieved_levels",
    "attach_director_l4_certification",
    "classify_claim_set",
    "evaluate_frozen_challenge",
    "freeze_candidate",
    "prepare_challenge",
    "unlock_ground_truth",
    "validate_challenge_id",
    "validate_compile_provenance",
    "validate_l4_certification",
    "verify_candidate_immutable",
]
