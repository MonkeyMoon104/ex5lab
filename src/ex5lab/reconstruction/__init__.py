"""Reconstruction research interfaces .

Provides an intermediate representation and MQ5 generator for *synthetic*
and *behavior-inferred* experiments. No EX5 opcode decoder is implemented.
BINARY_RECOVERED claims require a documented binary_range and are rejected
otherwise by ir_validation.
"""

from __future__ import annotations

from ex5lab.reconstruction.ir import (
    Assign,
    BasicBlock,
    BinOp,
    Branch,
    Call,
    Compare,
    Constant,
    Function,
    NameRef,
    ProgramIR,
    Provenance,
    Return,
    UnknownOp,
)
from ex5lab.reconstruction.ir_validation import IRValidationError, validate_program_ir
from ex5lab.reconstruction.mql5_generator import generate_mql5, load_fixture, write_mql5

# Still false: no verified executable-logic recovery from EX5 bytes.
RECONSTRUCTION_AVAILABLE = False


def status() -> dict:
    return {
        "reconstruction_available": False,
        "executable_logic_recovered": False,
        "ir_available": True,
        "mql5_generator_available": True,
        "ex5_opcode_decoder": False,
        "message": (
            "ProgramIR + MQ5 generator exist for synthetic/behavior-inferred research. "
            "No EX5 instruction decoder is implemented; do not claim binary recovery "
            "without evidence_status=BINARY_RECOVERED and binary_range."
        ),
    }


__all__ = [
    "RECONSTRUCTION_AVAILABLE",
    "status",
    "Assign",
    "BasicBlock",
    "BinOp",
    "Branch",
    "Call",
    "Compare",
    "Constant",
    "Function",
    "NameRef",
    "ProgramIR",
    "Provenance",
    "Return",
    "UnknownOp",
    "IRValidationError",
    "validate_program_ir",
    "generate_mql5",
    "load_fixture",
    "write_mql5",
]
