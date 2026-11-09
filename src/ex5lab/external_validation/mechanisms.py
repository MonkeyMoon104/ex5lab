"""Distinguish binary decompilation vs source retrieval vs reconstruction."""

from __future__ import annotations

from enum import Enum
from typing import Any


class MechanismHypothesis(str, Enum):
    BINARY_DECOMPILATION = "BINARY_DECOMPILATION"
    SOURCE_RETRIEVAL = "SOURCE_RETRIEVAL"
    SOURCE_RECONSTRUCTION = "SOURCE_RECONSTRUCTION"
    MECHANISM_UNKNOWN = "MECHANISM_UNKNOWN"


class ApiClaimCategory(str, Enum):
    OFFICIAL_API_VERIFIED = "OFFICIAL_API_VERIFIED"
    PRIVATE_API_CLAIM_UNVERIFIED = "PRIVATE_API_CLAIM_UNVERIFIED"
    PROPRIETARY_DECODER_CLAIM = "PROPRIETARY_DECODER_CLAIM"
    SOURCE_RETRIEVAL_MECHANISM_CLAIM = "SOURCE_RETRIEVAL_MECHANISM_CLAIM"
    MECHANISM_UNKNOWN = "MECHANISM_UNKNOWN"


def classify_claim_set(
    *,
    claims_genuine_ex5_decompile: bool = False,
    claims_mt_api_source_fetch: bool = False,
    official_public_api_documented: bool = False,
) -> dict[str, Any]:
    """Map developer assertions to scientific claim categories (not proof)."""
    categories: list[str] = []
    if claims_genuine_ex5_decompile:
        categories.append(ApiClaimCategory.PROPRIETARY_DECODER_CLAIM.value)
    if claims_mt_api_source_fetch:
        if official_public_api_documented:
            categories.append(ApiClaimCategory.OFFICIAL_API_VERIFIED.value)
        else:
            categories.append(ApiClaimCategory.PRIVATE_API_CLAIM_UNVERIFIED.value)
            categories.append(ApiClaimCategory.SOURCE_RETRIEVAL_MECHANISM_CLAIM.value)
    if not categories:
        categories.append(ApiClaimCategory.MECHANISM_UNKNOWN.value)

    return {
        "categories": categories,
        "hypothesis_space": [m.value for m in MechanismHypothesis],
        "notes": [
            "Developer statements are assertions, not verified implementation facts.",
            "L4 blind success does not automatically prove BINARY_DECOMPILATION (L5).",
            "Official MetaQuotes docs describe MQ5->EX5 compilation; they do not document "
            "a public API that returns original MQ5 for arbitrary EX5.",
        ],
        "official_public_api_documented": official_public_api_documented,
    }
