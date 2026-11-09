"""Binary analysis, stability, features, supervised evaluation."""

from ex5lab.analysis.stability import build_stability_atlas, apply_stable_mask, compare_on_stable_mask
from ex5lab.analysis.payload_features import extract_payload_features, feature_vector_family, FEATURE_FAMILIES
from ex5lab.analysis.eval_design import validate_supervised_design, validate_loo_feasibility, INVALID_EVALUATION_DESIGN
from ex5lab.analysis.supervised_eval import evaluate_heldout

__all__ = [
    "build_stability_atlas",
    "apply_stable_mask",
    "compare_on_stable_mask",
    "extract_payload_features",
    "feature_vector_family",
    "FEATURE_FAMILIES",
    "validate_supervised_design",
    "validate_loo_feasibility",
    "INVALID_EVALUATION_DESIGN",
    "evaluate_heldout",
]