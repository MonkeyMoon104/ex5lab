"""Generate MQ5 text from ProgramIR (research scaffolding only).

Never invents EX5 opcode decode. Output is always labeled with origin /
evidence_status so consumers cannot confuse it with binary recovery.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    Return,
    UnknownOp,
)
from ex5lab.reconstruction.ir_validation import validate_program_ir
from ex5lab.reconstruction.provenance import provenance_to_dict


def _escape_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _emit_expr(expr: Any) -> str:
    if isinstance(expr, Constant):
        if expr.kind == "string":
            return f'"{_escape_str(str(expr.value))}"'
        if expr.kind == "float":
            return repr(float(expr.value))
        return str(int(expr.value))
    if isinstance(expr, NameRef):
        return expr.name
    if isinstance(expr, BinOp):
        return f"({_emit_expr(expr.left)} {expr.op} {_emit_expr(expr.right)})"
    if isinstance(expr, Compare):
        return f"({_emit_expr(expr.left)} {expr.op} {_emit_expr(expr.right)})"
    if isinstance(expr, Call):
        args = ", ".join(_emit_expr(a) for a in expr.args)
        return f"{expr.callee}({args})"
    if isinstance(expr, UnknownOp):
        return f'/* UNKNOWN_OP:{expr.label} */ 0'
    raise TypeError(f"unsupported expr: {type(expr).__name__}")


def _emit_block_body(blk: BasicBlock, blocks_by_id: dict[str, BasicBlock], indent: str = "   ") -> list[str]:
    lines: list[str] = []
    for stmt in blk.statements:
        if isinstance(stmt, Assign):
            lines.append(f"{indent}{stmt.target} = {_emit_expr(stmt.value)};")
        elif isinstance(stmt, Call):
            lines.append(f"{indent}{_emit_expr(stmt)};")
        elif isinstance(stmt, Return):
            if stmt.value is None:
                lines.append(f"{indent}return;")
            else:
                lines.append(f"{indent}return {_emit_expr(stmt.value)};")
        elif isinstance(stmt, UnknownOp):
            lines.append(f"{indent}/* UNKNOWN_OP:{stmt.label} {stmt.raw_hint} */")
        elif isinstance(stmt, Branch):
            cond = _emit_expr(stmt.condition)
            lines.append(f"{indent}if({cond})")
            lines.append(f"{indent}  {{")
            then_blk = blocks_by_id.get(stmt.then_block)
            if then_blk is not None:
                lines.extend(_emit_block_body(then_blk, blocks_by_id, indent + "  "))
            lines.append(f"{indent}  }}")
            if stmt.else_block is not None:
                lines.append(f"{indent}else")
                lines.append(f"{indent}  {{")
                else_blk = blocks_by_id.get(stmt.else_block)
                if else_blk is not None:
                    lines.extend(_emit_block_body(else_blk, blocks_by_id, indent + "  "))
                lines.append(f"{indent}  }}")
        else:
            lines.append(f"{indent}/* unsupported stmt */")
    return lines


def _emit_function(fn: Function) -> list[str]:
    blocks_by_id = {b.block_id: b for b in fn.blocks}
    entry_id = fn.entry_block or (fn.blocks[0].block_id if fn.blocks else None)
    # Best-effort typed params (research scaffolding; defaults to int).
    params = ", ".join(f"int {p}" if p else p for p in fn.params)
    ret = fn.return_type if fn.return_type != "bool" else "bool"
    header = f"{ret} {fn.name}({params})"
    lines = [header, "  {"]
    # Declare simple locals from Assign targets (best-effort for scaffolding).
    locals_seen: set[str] = set()
    for blk in fn.blocks:
        for stmt in blk.statements:
            if isinstance(stmt, Assign) and stmt.target not in fn.params and stmt.target not in locals_seen:
                lines.append(f"   int {stmt.target}=0;")
                locals_seen.add(stmt.target)
    if entry_id and entry_id in blocks_by_id:
        # Emit entry; branch targets are inlined by Branch emitter (avoid double-emit of entry-only graph).
        emitted: set[str] = set()

        def emit_reachable(bid: str) -> None:
            if bid in emitted:
                return
            emitted.add(bid)
            blk = blocks_by_id[bid]
            # If block is only a branch target and already inlined, skip top-level re-emit
            # except entry.
            lines.extend(_emit_block_body(blk, blocks_by_id))
            for stmt in blk.statements:
                if isinstance(stmt, Branch):
                    # Targets already inlined inside if/else; mark visited.
                    emitted.add(stmt.then_block)
                    if stmt.else_block:
                        emitted.add(stmt.else_block)

        emit_reachable(entry_id)
    lines.append("  }")
    return lines


def generate_mql5(program: ProgramIR, *, validate: bool = True) -> str:
    """Emit MQ5 source text from ProgramIR."""
    if validate:
        validate_program_ir(program)

    prov = provenance_to_dict(program.provenance)
    header = [
        "// -*- coding: utf-8 -*-",
        "// =====================================================================",
        "// GENERATED FROM ProgramIR (ex5lab.reconstruction.mql5_generator)",
        f"// origin_label: {program.origin_label}",
        f"// evidence_status: {prov.get('evidence_status')}",
        f"// method: {prov.get('method')}",
        f"// experiment_id: {prov.get('experiment_id')}",
        f"// ex5_sha256: {prov.get('ex5_sha256')}",
        f"// binary_range: {prov.get('binary_range')}",
        "// NOT an EX5 opcode decode. Do not claim binary recovery without evidence.",
        "// =====================================================================",
        '#property copyright "ex5lab research"',
        '#property version   "1.00"',
        '#property script_show_inputs',
        "",
    ]

    body: list[str] = []
    for fn in program.functions:
        body.extend(_emit_function(fn))
        body.append("")

    # Minimal scaffolding if entry is missing common handlers.
    names = {f.name for f in program.functions}
    if program.program_kind == "script" and "OnStart" not in names:
        body.append("void OnStart()")
        body.append("  {")
        if program.entry_function and program.entry_function in names:
            body.append(f"   {program.entry_function}();")
        else:
            body.append('   Print("ProgramIR scaffold OnStart");')
        body.append("  }")
        body.append("")
    if program.program_kind == "expert" and "OnTick" not in names:
        body.append("void OnTick()")
        body.append("  {")
        body.append('   Comment("ProgramIR scaffold OnTick");')
        body.append("  }")
        body.append("")

    return "\n".join(header + body).rstrip() + "\n"


def program_ir_from_fixture_dict(data: dict[str, Any]) -> ProgramIR:
    """Load a minimal synthetic fixture JSON into ProgramIR.

    Fixture schema (research only):
      {
        "program_kind": "script",
        "entry_function": "OnStart",
        "provenance": {...},
        "functions": [
          {
            "name": "OnStart",
            "params": [],
            "return_type": "void",
            "entry_block": "entry",
            "blocks": [
              {
                "block_id": "entry",
                "statements": [
                  {"op": "assign", "target": "x", "value": {"op": "const", "kind": "int", "value": 1}},
                  {"op": "call", "callee": "Print", "args": [{"op": "name", "name": "x"}]}
                ]
              }
            ]
          }
        ]
      }
    """
    from ex5lab.reconstruction.provenance import make_provenance

    def load_prov(d: dict[str, Any] | None) -> Any:
        d = d or {}
        br = d.get("binary_range")
        binary_range = tuple(br) if br is not None else None
        return make_provenance(
            method=str(d.get("method", "fixture")),
            evidence_status=d.get("evidence_status", "HYPOTHETICAL"),  # type: ignore[arg-type]
            ex5_sha256=d.get("ex5_sha256"),
            binary_range=binary_range,  # type: ignore[arg-type]
            experiment_id=d.get("experiment_id"),
            notes=str(d.get("notes", "")),
        )

    def load_expr(d: dict[str, Any]) -> Any:
        op = d.get("op")
        if op == "const":
            return Constant(value=d["value"], kind=d.get("kind", "int"), provenance=load_prov(d.get("provenance")))
        if op == "name":
            return NameRef(name=d["name"], provenance=load_prov(d.get("provenance")))
        if op == "binop":
            return BinOp(
                op=d["operator"],
                left=load_expr(d["left"]),
                right=load_expr(d["right"]),
                provenance=load_prov(d.get("provenance")),
            )
        if op == "compare":
            return Compare(
                op=d["operator"],
                left=load_expr(d["left"]),
                right=load_expr(d["right"]),
                provenance=load_prov(d.get("provenance")),
            )
        if op == "call":
            return Call(
                callee=d["callee"],
                args=[load_expr(a) for a in d.get("args", [])],
                provenance=load_prov(d.get("provenance")),
            )
        if op == "unknown":
            return UnknownOp(label=d.get("label", "unknown"), raw_hint=d.get("raw_hint", ""), provenance=load_prov(d.get("provenance")))
        raise ValueError(f"unknown expr op: {op}")

    def load_stmt(d: dict[str, Any]) -> Any:
        op = d.get("op")
        if op == "assign":
            return Assign(target=d["target"], value=load_expr(d["value"]), provenance=load_prov(d.get("provenance")))
        if op == "branch":
            return Branch(
                condition=load_expr(d["condition"]),
                then_block=d["then_block"],
                else_block=d.get("else_block"),
                provenance=load_prov(d.get("provenance")),
            )
        if op == "return":
            val = d.get("value")
            return Return(value=load_expr(val) if val is not None else None, provenance=load_prov(d.get("provenance")))
        if op == "call":
            return load_expr(d)
        if op == "unknown":
            return load_expr(d)
        raise ValueError(f"unknown stmt op: {op}")

    functions: list[Function] = []
    for fd in data.get("functions", []):
        blocks = [
            BasicBlock(
                block_id=b["block_id"],
                statements=[load_stmt(s) for s in b.get("statements", [])],
                provenance=load_prov(b.get("provenance")),
            )
            for b in fd.get("blocks", [])
        ]
        functions.append(
            Function(
                name=fd["name"],
                params=list(fd.get("params", [])),
                blocks=blocks,
                entry_block=fd.get("entry_block"),
                return_type=fd.get("return_type", "void"),
                provenance=load_prov(fd.get("provenance")),
            )
        )

    return ProgramIR(
        functions=functions,
        program_kind=data.get("program_kind", "script"),
        entry_function=data.get("entry_function"),
        provenance=load_prov(data.get("provenance")),
        origin_label=data.get(
            "origin_label",
            "GENERATED_FROM_PROGRAM_IR  -  synthetic fixture; not EX5 decode.",
        ),
    )


def load_fixture(path: str | Path) -> ProgramIR:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return program_ir_from_fixture_dict(data)


def write_mql5(program: ProgramIR, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = generate_mql5(program)
    out.write_text(text, encoding="utf-8", newline="\n")
    return out
