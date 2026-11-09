"""reconstruction intermediate representation (synthetic / research).

This IR is for expressing *hypotheses* and *behavior-inferred* programs under
controlled experiments. It does **not** decode EX5 opcodes and must not claim
BINARY_RECOVERED without a documented binary_range and evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

EvidenceStatus = Literal[
    "BINARY_RECOVERED",
    "BEHAVIOR_INFERRED",
    "SOURCE_ASSISTED",
    "HYPOTHETICAL",
    "UNKNOWN",
]

EVIDENCE_STATUSES: frozenset[str] = frozenset(
    {
        "BINARY_RECOVERED",
        "BEHAVIOR_INFERRED",
        "SOURCE_ASSISTED",
        "HYPOTHETICAL",
        "UNKNOWN",
    }
)


@dataclass
class Provenance:
    """Where a reconstruction claim came from."""

    method: str = "unknown"
    evidence_status: EvidenceStatus = "UNKNOWN"
    ex5_sha256: str | None = None
    binary_range: tuple[int, int] | None = None  # inclusive start, exclusive end
    experiment_id: str | None = None
    notes: str = ""


@dataclass
class Constant:
    value: int | float | str
    kind: Literal["int", "float", "string"] = "int"
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class NameRef:
    name: str
    provenance: Provenance = field(default_factory=Provenance)


Expr = Union["Constant", "NameRef", "BinOp", "Compare", "Call", "UnknownOp"]


@dataclass
class BinOp:
    op: Literal["+", "-", "*", "/", "%"]
    left: Expr
    right: Expr
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class Compare:
    op: Literal["==", "!=", "<", "<=", ">", ">="]
    left: Expr
    right: Expr
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class Call:
    callee: str
    args: list[Expr] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class UnknownOp:
    """Placeholder when semantics are not recovered."""

    label: str = "unknown"
    raw_hint: str = ""
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class Branch:
    condition: Expr
    then_block: str  # basic-block id
    else_block: str | None = None
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class Return:
    value: Expr | None = None
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class Assign:
    target: str
    value: Expr
    provenance: Provenance = field(default_factory=Provenance)


Stmt = Union[Assign, Branch, Return, Call, UnknownOp]


@dataclass
class BasicBlock:
    block_id: str
    statements: list[Stmt] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class Function:
    name: str
    params: list[str] = field(default_factory=list)
    blocks: list[BasicBlock] = field(default_factory=list)
    entry_block: str | None = None
    return_type: Literal["void", "int", "float", "string", "bool"] = "void"
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class ProgramIR:
    """Top-level program IR with mandatory provenance discipline."""

    functions: list[Function] = field(default_factory=list)
    program_kind: Literal["script", "expert", "indicator", "unknown"] = "script"
    entry_function: str | None = None  # e.g. OnStart / OnTick
    provenance: Provenance = field(default_factory=Provenance)
    origin_label: str = (
        "GENERATED_FROM_PROGRAM_IR  -  not decoded from EX5 opcodes; "
        "do not treat as binary recovery unless evidence_status=BINARY_RECOVERED "
        "with a documented binary_range."
    )
