"""Decoder availability gate.

ex5lab does not ship a working EX5-to-ProgramIR instruction decoder.
Keep DECODER_AVAILABLE=False until an independently verified decoding rule exists.
"""

from __future__ import annotations

from typing import Any

from ex5lab.policy.static_only import assert_static_reconstruction_context, policy_status

DECODER_AVAILABLE = False
CURRENT_EVIDENCE_STATUS = "NO_EXECUTABLE_DECODING_EVIDENCE"


def decoder_status() -> dict[str, Any]:
    assert_static_reconstruction_context(uses_strategy_tester=False)
    return {
        "pipeline": [
            "EX5 File",
            "Verified Format Reader",
            "Executable Decoder",
            "Semantic Lifter",
            "ProgramIR",
            "MQL5 Generator",
        ],
        "format_reader_available": True,
        "executable_decoder_available": DECODER_AVAILABLE,
        "semantic_lifter_available": False,
        "program_ir_available": True,
        "mql5_generator_available": True,
        "evidence_status": CURRENT_EVIDENCE_STATUS,
        "strategy_tester_policy": policy_status()["strategy_tester_during_decode"],
        "message": (
            "Executable decoder unavailable: no independently validated "
            "instruction or CFG recovery rule for ordinary EX5 files."
        ),
    }


def decode_ex5_to_ir(_data: bytes, *, ex5_sha256: str | None = None) -> dict[str, Any]:
    """Refuse speculative decode. Never invents IR nodes."""
    assert_static_reconstruction_context(uses_strategy_tester=False)
    return {
        "ok": False,
        "ex5_sha256": ex5_sha256,
        "status": CURRENT_EVIDENCE_STATUS,
        "program_ir": None,
        "reason": "no_validated_executable_representation",
    }
