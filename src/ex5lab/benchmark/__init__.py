"""Independent source-oracle evaluation and evidence-integrity validation."""

from ex5lab.benchmark.scorer import score_case, score_blind_against_oracle
from ex5lab.benchmark.integrity import verify_freeze_bundle, IntegrityError

__all__ = [
    "score_case",
    "score_blind_against_oracle",
    "verify_freeze_bundle",
    "IntegrityError",
]
