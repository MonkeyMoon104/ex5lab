"""Production vs research boundary for MetaTrader tooling.

The production ex5lab path must remain:

    EX5 file -> offline decoder -> semantic IR -> ProgramIR -> MQ5

Strategy Tester, MetaEditor, and live terminal execution may be used as
*research instruments* by contributors, but a claimed decoder must not depend
on them at runtime.
"""

from __future__ import annotations

from typing import Any

RESEARCH_TESTER_ALLOWED = True
PRODUCTION_DECODE_TESTER_FORBIDDEN = True


class StaticOnlyPolicyError(RuntimeError):
    """Raised when a production decode path depends on forbidden runtime tools."""


def assert_static_reconstruction_context(*, uses_strategy_tester: bool) -> None:
    if uses_strategy_tester and PRODUCTION_DECODE_TESTER_FORBIDDEN:
        raise StaticOnlyPolicyError(
            "Production EX5 decode must not depend on Strategy Tester. "
            "Use the tester only for separate research experiments."
        )


def policy_status() -> dict[str, Any]:
    return {
        "research_tester_allowed": RESEARCH_TESTER_ALLOWED,
        "strategy_tester_during_decode": "forbidden",
        "production_pipeline": [
            "EX5 File",
            "Offline Decoder",
            "Semantic IR",
            "ProgramIR",
            "MQ5",
        ],
        "note": (
            "Research tooling is not the product. Demonstrated offline decoding "
            "is required before claiming recovery."
        ),
    }
