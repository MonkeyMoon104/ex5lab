"""Validate ProgramIR structure and provenance discipline."""

from __future__ import annotations

from typing import Any

from ex5lab.reconstruction.ir import (
    EVIDENCE_STATUSES,
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


class IRValidationError(ValueError):
    """Raised when IR structure or provenance claims are invalid."""


def _check_provenance(p: Provenance, where: str, errors: list[str]) -> None:
    if p.evidence_status not in EVIDENCE_STATUSES:
        errors.append(f"{where}: invalid evidence_status {p.evidence_status!r}")
    if p.evidence_status == "BINARY_RECOVERED":
        if p.binary_range is None:
            errors.append(
                f"{where}: BINARY_RECOVERED requires binary_range; "
                "refuse unsupported recovery claim"
            )
        else:
            start, end = p.binary_range
            if start < 0 or end <= start:
                errors.append(f"{where}: binary_range must be [start, end) with end > start >= 0")
        if not p.ex5_sha256:
            errors.append(f"{where}: BINARY_RECOVERED requires ex5_sha256")


def _walk_expr(expr: Any, where: str, errors: list[str]) -> None:
    if isinstance(expr, Constant):
        _check_provenance(expr.provenance, f"{where}.const", errors)
        if expr.kind == "int" and not isinstance(expr.value, int):
            errors.append(f"{where}: int constant value must be int")
        if expr.kind == "float" and not isinstance(expr.value, (int, float)):
            errors.append(f"{where}: float constant value must be numeric")
        if expr.kind == "string" and not isinstance(expr.value, str):
            errors.append(f"{where}: string constant value must be str")
        return
    if isinstance(expr, NameRef):
        if not expr.name:
            errors.append(f"{where}: empty NameRef")
        _check_provenance(expr.provenance, f"{where}.nameref", errors)
        return
    if isinstance(expr, BinOp):
        _check_provenance(expr.provenance, f"{where}.binop", errors)
        _walk_expr(expr.left, f"{where}.left", errors)
        _walk_expr(expr.right, f"{where}.right", errors)
        return
    if isinstance(expr, Compare):
        _check_provenance(expr.provenance, f"{where}.compare", errors)
        _walk_expr(expr.left, f"{where}.left", errors)
        _walk_expr(expr.right, f"{where}.right", errors)
        return
    if isinstance(expr, Call):
        if not expr.callee:
            errors.append(f"{where}: empty Call.callee")
        _check_provenance(expr.provenance, f"{where}.call", errors)
        for i, a in enumerate(expr.args):
            _walk_expr(a, f"{where}.arg[{i}]", errors)
        return
    if isinstance(expr, UnknownOp):
        _check_provenance(expr.provenance, f"{where}.unknown", errors)
        return
    errors.append(f"{where}: unsupported expression type {type(expr).__name__}")


def validate_program_ir(program: ProgramIR, *, raise_on_error: bool = True) -> list[str]:
    """Validate IR structure. Returns error list; optionally raises."""
    errors: list[str] = []
    _check_provenance(program.provenance, "program", errors)

    if not program.functions:
        errors.append("program: no functions")

    fn_names = [f.name for f in program.functions]
    if len(fn_names) != len(set(fn_names)):
        errors.append("program: duplicate function names")

    if program.entry_function and program.entry_function not in fn_names:
        errors.append(f"program: entry_function {program.entry_function!r} not found")

    for fn in program.functions:
        _check_provenance(fn.provenance, f"fn:{fn.name}", errors)
        if not fn.name:
            errors.append("function: empty name")
        block_ids = [b.block_id for b in fn.blocks]
        if len(block_ids) != len(set(block_ids)):
            errors.append(f"fn:{fn.name}: duplicate block ids")
        if fn.entry_block and fn.entry_block not in block_ids:
            errors.append(f"fn:{fn.name}: entry_block {fn.entry_block!r} missing")
        if not fn.blocks:
            errors.append(f"fn:{fn.name}: no basic blocks")

        for blk in fn.blocks:
            _check_provenance(blk.provenance, f"fn:{fn.name}.bb:{blk.block_id}", errors)
            if not blk.block_id:
                errors.append(f"fn:{fn.name}: empty block_id")
            for i, stmt in enumerate(blk.statements):
                where = f"fn:{fn.name}.bb:{blk.block_id}.stmt[{i}]"
                if isinstance(stmt, Assign):
                    if not stmt.target:
                        errors.append(f"{where}: empty assign target")
                    _check_provenance(stmt.provenance, where, errors)
                    _walk_expr(stmt.value, where, errors)
                elif isinstance(stmt, Branch):
                    _check_provenance(stmt.provenance, where, errors)
                    _walk_expr(stmt.condition, f"{where}.cond", errors)
                    if stmt.then_block not in block_ids:
                        errors.append(f"{where}: then_block {stmt.then_block!r} missing")
                    if stmt.else_block is not None and stmt.else_block not in block_ids:
                        errors.append(f"{where}: else_block {stmt.else_block!r} missing")
                elif isinstance(stmt, Return):
                    _check_provenance(stmt.provenance, where, errors)
                    if stmt.value is not None:
                        _walk_expr(stmt.value, f"{where}.ret", errors)
                elif isinstance(stmt, Call):
                    _walk_expr(stmt, where, errors)
                elif isinstance(stmt, UnknownOp):
                    _check_provenance(stmt.provenance, where, errors)
                else:
                    errors.append(f"{where}: unsupported statement {type(stmt).__name__}")

    if raise_on_error and errors:
        raise IRValidationError("; ".join(errors))
    return errors


def assert_no_unsupported_binary_recovery(program: ProgramIR) -> None:
    """Convenience: reject BINARY_RECOVERED without binary_range anywhere in program."""
    errors = validate_program_ir(program, raise_on_error=False)
    bad = [e for e in errors if "BINARY_RECOVERED" in e]
    if bad:
        raise IRValidationError("; ".join(bad))
