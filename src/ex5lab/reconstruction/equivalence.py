"""Behavioral equivalence helpers for pure expression IR (no live trading).

Compares numeric/string outputs of simple pure functions under test vectors.
This is research scaffolding  -  not proof of EX5 recovery.
"""

from __future__ import annotations

from typing import Any, Callable

from ex5lab.reconstruction.ir import (
    Assign,
    BinOp,
    Branch,
    Call,
    Compare,
    Constant,
    Function,
    NameRef,
    ProgramIR,
    Return,
    UnknownOp,
)


class EquivalenceError(RuntimeError):
    pass


def eval_expr(expr: Any, env: dict[str, Any]) -> Any:
    if isinstance(expr, Constant):
        return expr.value
    if isinstance(expr, NameRef):
        if expr.name not in env:
            raise EquivalenceError(f"unbound name: {expr.name}")
        return env[expr.name]
    if isinstance(expr, BinOp):
        left = eval_expr(expr.left, env)
        right = eval_expr(expr.right, env)
        if expr.op == "+":
            return left + right
        if expr.op == "-":
            return left - right
        if expr.op == "*":
            return left * right
        if expr.op == "/":
            return left / right
        if expr.op == "%":
            return left % right
        raise EquivalenceError(f"unsupported binop {expr.op}")
    if isinstance(expr, Compare):
        left = eval_expr(expr.left, env)
        right = eval_expr(expr.right, env)
        ops: dict[str, Callable[[Any, Any], bool]] = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }
        return ops[expr.op](left, right)
    if isinstance(expr, Call):
        # Pure subset: only allow identity-like helpers used in tests.
        if expr.callee in {"int", "double", "string"}:
            return eval_expr(expr.args[0], env) if expr.args else None
        raise EquivalenceError(f"non-pure or unsupported call: {expr.callee}")
    if isinstance(expr, UnknownOp):
        raise EquivalenceError(f"cannot evaluate UnknownOp: {expr.label}")
    raise EquivalenceError(f"unsupported expr type: {type(expr).__name__}")


def eval_function_pure(fn: Function, args: dict[str, Any]) -> Any:
    """Evaluate a single-entry function with optional simple if/return (no loops)."""
    if not fn.blocks:
        raise EquivalenceError("no blocks")
    blocks = {b.block_id: b for b in fn.blocks}
    entry = fn.entry_block or fn.blocks[0].block_id
    env = dict(args)
    bid = entry
    visited = 0
    while bid is not None:
        visited += 1
        if visited > 64:
            raise EquivalenceError("control-flow budget exceeded (possible cycle)")
        blk = blocks[bid]
        next_bid: str | None = None
        for stmt in blk.statements:
            if isinstance(stmt, Assign):
                env[stmt.target] = eval_expr(stmt.value, env)
            elif isinstance(stmt, Return):
                if stmt.value is None:
                    return None
                return eval_expr(stmt.value, env)
            elif isinstance(stmt, Branch):
                cond = bool(eval_expr(stmt.condition, env))
                next_bid = stmt.then_block if cond else stmt.else_block
                break
            elif isinstance(stmt, Call):
                eval_expr(stmt, env)
            elif isinstance(stmt, UnknownOp):
                raise EquivalenceError("UnknownOp in function body")
            else:
                raise EquivalenceError(f"unsupported stmt: {type(stmt).__name__}")
        bid = next_bid
    return None


def compare_outputs(
    expected: Any,
    actual: Any,
    *,
    float_tol: float = 1e-9,
) -> dict[str, Any]:
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            ok = abs(float(expected) - float(actual)) <= float_tol
        except (TypeError, ValueError):
            ok = False
        return {"equal": ok, "expected": expected, "actual": actual, "kind": "float"}
    if isinstance(expected, str) or isinstance(actual, str):
        ok = str(expected) == str(actual)
        return {"equal": ok, "expected": expected, "actual": actual, "kind": "string"}
    ok = expected == actual
    return {"equal": ok, "expected": expected, "actual": actual, "kind": "numeric"}


def run_test_vectors(
    fn: Function,
    vectors: list[dict[str, Any]],
    *,
    float_tol: float = 1e-9,
) -> dict[str, Any]:
    """Each vector: {\"args\": {...}, \"expected\": value}."""
    results = []
    all_ok = True
    for i, vec in enumerate(vectors):
        args = vec.get("args") or {}
        expected = vec["expected"]
        try:
            actual = eval_function_pure(fn, args)
            cmp = compare_outputs(expected, actual, float_tol=float_tol)
        except EquivalenceError as exc:
            cmp = {"equal": False, "error": str(exc), "expected": expected, "actual": None}
        if not cmp.get("equal"):
            all_ok = False
        results.append({"index": i, **cmp})
    return {
        "schema": "phase10_equivalence_v1",
        "function": fn.name,
        "n_vectors": len(vectors),
        "all_equal": all_ok,
        "results": results,
        "disclaimer": (
            "Pure-Python IR evaluation only; not live trading; "
            "not proof of EX5 binary recovery."
        ),
    }


def compare_program_functions(
    left: ProgramIR,
    right: ProgramIR,
    function_name: str,
    vectors: list[dict[str, Any]],
) -> dict[str, Any]:
    lf = next((f for f in left.functions if f.name == function_name), None)
    rf = next((f for f in right.functions if f.name == function_name), None)
    if lf is None or rf is None:
        return {
            "all_equal": False,
            "error": f"function {function_name!r} missing on one side",
        }
    left_out = []
    right_out = []
    pairs = []
    all_ok = True
    for i, vec in enumerate(vectors):
        args = vec.get("args") or {}
        try:
            lo = eval_function_pure(lf, args)
            ro = eval_function_pure(rf, args)
            cmp = compare_outputs(lo, ro)
        except EquivalenceError as exc:
            cmp = {"equal": False, "error": str(exc)}
            lo = ro = None
        left_out.append(lo)
        right_out.append(ro)
        if not cmp.get("equal"):
            all_ok = False
        pairs.append({"index": i, "args": args, **cmp})
    return {
        "schema": "phase10_equivalence_pair_v1",
        "function": function_name,
        "all_equal": all_ok,
        "pairs": pairs,
        "disclaimer": "IR-to-IR pure eval; no MetaTrader execution; no EX5 decode claim.",
    }
