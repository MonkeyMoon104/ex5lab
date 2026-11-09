"""Scaffold tiny MQL5 Script programs for semantic-control families.

Writes self-authored sources under corpus/phase10/sources/ (or a caller path).
No EX5 decode; sources are intentionally minimal for differential experiments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCES = ROOT / "corpus" / "phase10" / "sources"

# Pairwise experiment matrix (planned). Compilation may be deferred.
EXPERIMENT_PAIRS: list[dict[str, Any]] = [
    {
        "pair_id": "arith_add",
        "family": "arithmetic",
        "a": "arith_add1.mq5",
        "b": "arith_add2.mq5",
        "source_change": "return/print x+1 vs x+2 via input",
        "expected_behavior_delta": "Printed sum differs by +1 for same input",
    },
    {
        "pair_id": "branch_gt",
        "family": "branch",
        "a": "branch_gt10.mq5",
        "b": "branch_gt20.mq5",
        "source_change": "threshold 10 vs 20 in comparison",
        "expected_behavior_delta": "Branch outcome flips for inputs in (10,20]",
    },
    {
        "pair_id": "const_lit",
        "family": "constant",
        "a": "const_lit_1.mq5",
        "b": "const_lit_2.mq5",
        "source_change": "literal constant 1 vs 2",
        "expected_behavior_delta": "Printed constant differs",
    },
    {
        "pair_id": "meta_only",
        "family": "metadata",
        "a": "meta_only_A.mq5",
        "b": "meta_only_B.mq5",
        "source_change": "copyright/version property only",
        "expected_behavior_delta": "Observable Print identical; metadata fields differ",
    },
]


def _script(copyright: str, version: str, body: str) -> str:
    return "\n".join(
        [
            f'#property copyright "{copyright}"',
            f'#property version   "{version}"',
            "#property script_show_inputs",
            "void OnStart()",
            "  {",
            body,
            "  }",
            "",
        ]
    )


def _script_with_input(copyright: str, version: str, input_line: str, body: str) -> str:
    return "\n".join(
        [
            f'#property copyright "{copyright}"',
            f'#property version   "{version}"',
            "#property script_show_inputs",
            input_line,
            "void OnStart()",
            "  {",
            body,
            "  }",
            "",
        ]
    )


SOURCE_TEMPLATES: dict[str, str] = {
    "arith_add1.mq5": _script_with_input(
        "ex5lab arith_add1",
        "1.00",
        "input int x=3;",
        "   int y=x+1;\n"
        '   Print("arith_add1=",y);\n'
        '   Comment("arith_add1=",y);',
    ),
    "arith_add2.mq5": _script_with_input(
        "ex5lab arith_add2",
        "1.00",
        "input int x=3;",
        "   int y=x+2;\n"
        '   Print("arith_add2=",y);\n'
        '   Comment("arith_add2=",y);',
    ),
    "branch_gt10.mq5": _script_with_input(
        "ex5lab branch_gt10",
        "1.00",
        "input int x=15;",
        '   string s=(x>10)?"gt":"le";\n'
        '   Print("branch_gt10=",s);\n'
        '   Comment("branch_gt10=",s);',
    ),
    "branch_gt20.mq5": _script_with_input(
        "ex5lab branch_gt20",
        "1.00",
        "input int x=15;",
        '   string s=(x>20)?"gt":"le";\n'
        '   Print("branch_gt20=",s);\n'
        '   Comment("branch_gt20=",s);',
    ),
    "const_lit_1.mq5": _script(
        "ex5lab const_lit_1",
        "1.00",
        "   int c=1;\n"
        '   Print("const_lit=",c);\n'
        '   Comment("const_lit=",c);',
    ),
    "const_lit_2.mq5": _script(
        "ex5lab const_lit_2",
        "1.00",
        "   int c=2;\n"
        '   Print("const_lit=",c);\n'
        '   Comment("const_lit=",c);',
    ),
    "meta_only_A.mq5": _script(
        "ex5lab MetaA",
        "1.00",
        '   Print("meta_only_ok");\n'
        '   Comment("meta_only_ok");',
    ),
    "meta_only_B.mq5": _script(
        "ex5lab MetaB",
        "2.00",
        '   Print("meta_only_ok");\n'
        '   Comment("meta_only_ok");',
    ),
}


def write_phase10_sources(out_dir: str | Path | None = None) -> dict[str, Any]:
    """Write all semantic-control MQ5 sources (UTF-8)."""
    dest = Path(out_dir) if out_dir else DEFAULT_SOURCES
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, text in SOURCE_TEMPLATES.items():
        path = dest / name
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(str(path))
    return {
        "schema": "phase10_semantic_controls_v1",
        "out_dir": str(dest),
        "written": written,
        "pairs": EXPERIMENT_PAIRS,
        "note": "Self-authored MQ5 scripts for differential experiments; not recovered from EX5.",
    }


def planned_experiment_matrix() -> dict[str, Any]:
    return {
        "schema": "phase10_differential_plan_v1",
        "sources": sorted(SOURCE_TEMPLATES.keys()),
        "pairs": EXPERIMENT_PAIRS,
        "compile_required_for_ex5": True,
        "status": "planned",
        "disclaimer": (
            "Plan only until MetaEditor compilation produces EX5 artifacts. "
            "No binary recovery claims without measured deltas."
        ),
    }
