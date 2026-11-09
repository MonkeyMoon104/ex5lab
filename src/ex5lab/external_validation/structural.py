"""Executable-aware structural comparison for external MQ5 candidates.

Conservative subset analyzer:
- Ignores comments and string-literal interiors when mining operators/literals.
- Compares function bodies reached from entry handlers (dead helpers do not count).
- Compares simple expression ASTs for return/assignment expressions.
- Returns UNVERIFIED rather than inventing full semantic equivalence.

Does NOT claim full MQL5 semantic equivalence.
"""

from __future__ import annotations

import re
from typing import Any

from ex5lab.external_validation.lex import executable_code_only

_ENTRY = frozenset({"OnInit", "OnTick", "OnDeinit", "OnTimer", "OnTrade", "OnChartEvent"})
_TYPE = r"(?:int|double|bool|void|string|long|ulong|datetime|char|short|uchar|ushort|uint|float)"
_FUNC_HEAD = re.compile(
    rf"\b{_TYPE}\s+([A-Za-z_]\w*)\s*\(([^;]*?)\)\s*\{{",
    re.S,
)
_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_RETURN_RE = re.compile(r"\breturn\s*(\((?:[^;()]|\([^;()]*\))*\)|[^;]+)\s*;", re.S)
_ASSIGN_RE = re.compile(
    rf"\b{_TYPE}\s+[A-Za-z_]\w*\s*=\s*([^;]+);",
    re.S,
)
_INCLUDE_RE = re.compile(r"^\s*#\s*include\b", re.M | re.I)
_DEFINE_RE = re.compile(r"^\s*#\s*define\b", re.M | re.I)
_COND_PP_RE = re.compile(r"^\s*#\s*(?:if|ifdef|ifndef|elif|else|endif)\b", re.M | re.I)
_PROPERTY_RE = re.compile(r"^\s*#\s*property\b", re.M | re.I)


def _brace_body(text: str, open_brace_index: int) -> str | None:
    if open_brace_index < 0 or open_brace_index >= len(text) or text[open_brace_index] != "{":
        return None
    depth = 0
    for i in range(open_brace_index, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_index + 1 : i]
    return None


def extract_functions(code: str) -> dict[str, dict[str, Any]]:
    """Map function name -> {params, body, start} from executable code only."""
    found: dict[str, dict[str, Any]] = {}
    for m in _FUNC_HEAD.finditer(code):
        name = m.group(1)
        params = re.sub(r"\s+", " ", m.group(2)).strip()
        body = _brace_body(code, m.end() - 1)
        if body is None:
            continue
        found[name] = {"params": params, "body": body, "start": m.start()}
    return found


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _tokenize_expr(s: str) -> list[str]:
    s = s.strip()
    if s.startswith("(") and s.endswith(")") and _balanced(s[1:-1]):
        # keep parens as structure via recursive parse; strip only outer if fully wrapping
        pass
    tokens: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "+-*/%()":
            tokens.append(ch)
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < len(s) and s[i + 1].isdigit()):
            j = i + 1
            while j < len(s) and (s[j].isdigit() or s[j] == "."):
                j += 1
            tokens.append(s[i:j])
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            tokens.append(s[i:j])
            i = j
            continue
        # Unknown char  -  keep as singleton so mismatch surfaces
        tokens.append(ch)
        i += 1
    return tokens


def _balanced(s: str) -> bool:
    d = 0
    for ch in s:
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
            if d < 0:
                return False
    return d == 0


def parse_expr_ast(expr: str) -> Any | None:
    """Parse a narrow arithmetic/call expression into a nested tuple AST."""
    tokens = _tokenize_expr(expr)
    if not tokens:
        return None
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def eat(expected: str | None = None) -> str | None:
        nonlocal pos
        tok = peek()
        if expected is not None and tok != expected:
            return None
        if tok is None:
            return None
        pos += 1
        return tok

    def parse_primary() -> Any | None:
        tok = peek()
        if tok is None:
            return None
        if tok == "(":
            eat("(")
            node = parse_add()
            if eat(")") is None:
                return None
            return node
        if tok == "-":
            eat("-")
            inner = parse_primary()
            return ("neg", inner) if inner is not None else None
        if re.fullmatch(r"\d+(?:\.\d+)?", tok or ""):
            eat()
            return ("num", tok)
        if re.fullmatch(r"[A-Za-z_]\w*", tok or ""):
            name = eat()
            if peek() == "(":
                eat("(")
                args: list[Any] = []
                if peek() != ")":
                    while True:
                        arg = parse_add()
                        if arg is None:
                            return None
                        args.append(arg)
                        if peek() == ",":
                            eat(",")
                            continue
                        break
                if eat(")") is None:
                    return None
                return ("call", name, tuple(args))
            return ("id", name)
        return None

    def parse_mul() -> Any | None:
        left = parse_primary()
        if left is None:
            return None
        while peek() in ("*", "/", "%"):
            op = eat()
            right = parse_primary()
            if right is None:
                return None
            left = ("binop", op, left, right)
        return left

    def parse_add() -> Any | None:
        left = parse_mul()
        if left is None:
            return None
        while peek() in ("+", "-"):
            op = eat()
            right = parse_mul()
            if right is None:
                return None
            left = ("binop", op, left, right)
        return left

    tree = parse_add()
    if tree is None or pos != len(tokens):
        return None
    return tree


def _exprs_from_body(body: str) -> list[str]:
    exprs: list[str] = []
    for m in _RETURN_RE.finditer(body):
        raw = m.group(1).strip()
        if raw.startswith("(") and raw.endswith(")") and _balanced(raw[1:-1]):
            raw = raw[1:-1].strip()
        exprs.append(raw)
    for m in _ASSIGN_RE.finditer(body):
        exprs.append(m.group(1).strip())
    return exprs


def _body_fingerprint(body: str) -> str:
    return _normalize_ws(body)


def _calls_in_body(body: str, known: set[str]) -> set[str]:
    return {n for n in _CALL_RE.findall(body) if n in known and n not in _ENTRY}


def reachable_from_entries(functions: dict[str, dict[str, Any]]) -> set[str]:
    known = set(functions)
    stack = [n for n in _ENTRY if n in functions]
    seen: set[str] = set()
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        body = functions[name]["body"]
        for callee in _calls_in_body(body, known):
            if callee not in seen:
                stack.append(callee)
    return seen


def _preprocessor_flags(text: str) -> dict[str, Any]:
    """Detect preprocessor constructs outside the reliably interpreted subset."""
    codeish = executable_code_only(text, blank_strings=True)
    includes = _INCLUDE_RE.findall(codeish)
    defines = _DEFINE_RE.findall(codeish)
    cond_pp = _COND_PP_RE.findall(codeish)
    # #property is metadata  -  recorded but not treated as unsupported by itself
    properties = sorted(
        {
            m.group(0).strip()
            for m in re.finditer(r"^\s*#\s*property\b[^\n]*", codeish, re.M | re.I)
        }
    )
    unsupported: list[str] = []
    if includes:
        unsupported.append("include")
    if defines:
        unsupported.append("define_macro")
    if cond_pp:
        unsupported.append("conditional_compilation")
    return {
        "include_count": len(includes),
        "define_count": len(defines),
        "conditional_pp_count": len(cond_pp),
        "properties": properties,
        "unsupported_constructs": sorted(set(unsupported)),
        "preprocessor_fingerprint": _body_fingerprint(
            "\n".join(
                line.strip()
                for line in codeish.splitlines()
                if line.strip().startswith("#") and not _PROPERTY_RE.match(line)
            )
        ),
    }


def extract_structural_profile(text: str) -> dict[str, Any]:
    """Executable-code profile (comments/strings excluded from feature mining)."""
    code = executable_code_only(text, blank_strings=True)
    functions = extract_functions(code)
    reachable = reachable_from_entries(functions)
    entry_handlers = sorted(n for n in functions if n in _ENTRY)

    # Features mined only from reachable executable bodies (+ empty if none)
    reachable_bodies = "\n".join(functions[n]["body"] for n in sorted(reachable))
    feature_src = reachable_bodies if reachable_bodies.strip() else ""

    helpers_reachable = sorted(n for n in reachable if n not in _ENTRY)
    helpers_all = sorted(n for n in functions if n not in _ENTRY)

    expr_asts: dict[str, list[Any]] = {}
    body_fps: dict[str, str] = {}
    for name in sorted(reachable):
        body = functions[name]["body"]
        body_fps[name] = _body_fingerprint(body)
        trees: list[Any] = []
        for expr in _exprs_from_body(body):
            ast = parse_expr_ast(expr)
            if ast is not None:
                trees.append(ast)
        expr_asts[name] = trees

    # Entry handler fingerprints include empty bodies (presence matters).
    entry_fps = {
        n: _body_fingerprint(functions[n]["body"]) for n in entry_handlers
    }

    pp = _preprocessor_flags(text)

    return {
        "entry_handlers": entry_handlers,
        "entry_body_fingerprints": entry_fps,
        "helpers_all_defined": helpers_all,
        "helpers_reachable": helpers_reachable,
        "reachable_functions": sorted(reachable),
        "body_fingerprints": body_fps,
        "expression_asts": {k: [str(t) for t in v] for k, v in expr_asts.items()},
        "expression_asts_raw": expr_asts,
        "has_if": bool(re.search(r"\bif\s*\(", feature_src)),
        "has_else": bool(re.search(r"\belse\b", feature_src)),
        "has_for": bool(re.search(r"\bfor\s*\(", feature_src)),
        "has_while": bool(re.search(r"\bwhile\s*\(", feature_src)),
        "comparisons": sorted(
            {op for op in ("==", "!=", "<=", ">=", "<", ">") if op in feature_src}
        ),
        "arith_ops": sorted({op for op in ("+", "-", "*", "/", "%") if op in feature_src}),
        "int_literals": sorted(
            {int(x) for x in re.findall(r"(?<![\w.])(\d+)(?![\w.])", feature_src)}
        )[:40],
        "print_markers": sorted(
            set(
                re.findall(
                    r'Print\s*\(\s*"([^"]*)"',
                    executable_code_only(text, blank_strings=False),
                )
            )
        ),
        "preprocessor": pp,
        "unsupported_constructs": list(pp["unsupported_constructs"]),
        "parser_coverage": "executable_subset_lex_ast_v3",
        "full_ast": False,
        "code_only_sha_prefix": _body_fingerprint(code)[:32],
        "supported_subset_note": (
            "Supports entry-handler set equality, reachable helper bodies, and narrow "
            "arithmetic/call expression ASTs. Does not interpret #include/#define/#if, "
            "macros, or full MQL5 control-flow / data dependence."
        ),
    }


def compare_profiles(expected: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare executable structural profiles; conservative L3 gating (fail closed)."""
    matches: list[str] = []
    mismatches: list[str] = []
    unverified: list[str] = [
        "full_control_flow_graph",
        "variable_data_dependence",
        "complete_mql5_semantics",
        "dead_code_aside_from_entry_reachability",
        "macro_and_include_expansion",
        "full_semantic_equivalence",
    ]

    exp_entries = set(expected.get("entry_handlers") or [])
    got_entries = set(candidate.get("entry_handlers") or [])
    exp_reach = set(expected.get("reachable_functions") or [])
    got_reach = set(candidate.get("reachable_functions") or [])
    exp_helpers = set(expected.get("helpers_reachable") or [])
    got_helpers = set(candidate.get("helpers_reachable") or [])

    # Exact entry-handler set equality  -  unexpected OnTrade/OnTimer/OnChartEvent fail.
    if got_entries == exp_entries:
        matches.append("entry_handlers_equal")
    else:
        extra = got_entries - exp_entries
        missing = exp_entries - got_entries
        if extra:
            mismatches.append("unexpected_entry_handlers:" + ",".join(sorted(extra)))
        if missing:
            mismatches.append("missing_entry_handlers:" + ",".join(sorted(missing)))

    exp_entry_fps: dict[str, str] = expected.get("entry_body_fingerprints") or {}
    got_entry_fps: dict[str, str] = candidate.get("entry_body_fingerprints") or {}
    for name in sorted(exp_entries | got_entries):
        if exp_entry_fps.get(name) == got_entry_fps.get(name) and name in exp_entries and name in got_entries:
            matches.append(f"entry_body_fp:{name}")
        elif name in exp_entries and name in got_entries:
            mismatches.append(f"entry_body_fp_mismatch:{name}")

    # Reachable set must match  -  extra reachable helpers are unexpected side-effect surface.
    if got_reach == exp_reach:
        matches.append("reachable_set_equal")
    else:
        extra_r = got_reach - exp_reach
        missing_r = exp_reach - got_reach
        if extra_r:
            mismatches.append("unexpected_reachable_functions:" + ",".join(sorted(extra_r)))
        if missing_r:
            mismatches.append("missing_reachable_functions:" + ",".join(sorted(missing_r)))

    if exp_helpers == got_helpers:
        if exp_helpers:
            matches.append("reachable_helpers_equal")
    else:
        if exp_helpers - got_helpers:
            mismatches.append(
                "reachable_helpers_missing:" + ",".join(sorted(exp_helpers - got_helpers))
            )
        if got_helpers - exp_helpers:
            mismatches.append(
                "unexpected_reachable_helpers:" + ",".join(sorted(got_helpers - exp_helpers))
            )

    dead_only_overlap = (
        set(candidate.get("helpers_all_defined") or []) - got_helpers
    ) & set(expected.get("helpers_all_defined") or [])
    if dead_only_overlap and not (exp_helpers <= got_helpers):
        mismatches.append(
            "helpers_only_in_dead_code:" + ",".join(sorted(dead_only_overlap))
        )

    exp_fps: dict[str, str] = expected.get("body_fingerprints") or {}
    got_fps: dict[str, str] = candidate.get("body_fingerprints") or {}
    exp_asts: dict[str, list[Any]] = expected.get("expression_asts_raw") or {}
    got_asts: dict[str, list[Any]] = candidate.get("expression_asts_raw") or {}

    body_matches = 0
    required_bodies = [n for n in sorted(exp_reach) if exp_fps.get(n, "") not in ("",)]
    for name in required_bodies:
        if got_fps.get(name) == exp_fps.get(name):
            body_matches += 1
            matches.append(f"body_fp:{name}")
        else:
            mismatches.append(f"body_fp_mismatch:{name}")

    ast_required = 0
    ast_ok = 0
    for name, trees in exp_asts.items():
        if not trees:
            continue
        ast_required += 1
        if got_asts.get(name) == trees:
            ast_ok += 1
            matches.append(f"expr_ast:{name}")
        else:
            mismatches.append(f"expr_ast_mismatch:{name}")

    for key, label in (
        ("has_if", "if_present"),
        ("has_else", "else_present"),
        ("has_for", "for_present"),
        ("has_while", "while_present"),
    ):
        if expected.get(key):
            if candidate.get(key):
                matches.append(label)
            else:
                mismatches.append(f"missing_{label}")

    exp_prints = set(expected.get("print_markers") or [])
    got_prints = set(candidate.get("print_markers") or [])
    if exp_prints:
        if exp_prints <= got_prints:
            matches.append("print_markers_executable")
        else:
            mismatches.append(
                "print_markers_missing:" + ",".join(sorted(exp_prints - got_prints))
            )

    exp_arith = set(expected.get("arith_ops") or [])
    got_arith = set(candidate.get("arith_ops") or [])
    if exp_arith:
        if exp_arith <= got_arith:
            matches.append("arith_ops_reachable_overlap")
        else:
            mismatches.append(
                "arith_ops_missing:" + ",".join(sorted(exp_arith - got_arith))
            )

    distinctive = {n for n in (expected.get("int_literals") or []) if n >= 10}
    got_ints = set(candidate.get("int_literals") or [])
    if distinctive:
        if distinctive <= got_ints:
            matches.append("distinctive_int_literals_reachable")
        else:
            mismatches.append(
                "distinctive_int_literals_missing:"
                + ",".join(str(x) for x in sorted(distinctive - got_ints))
            )

    # Preprocessor / macros / includes  -  fail closed (UNVERIFIED), never VERIFIED.
    exp_unsup = set(expected.get("unsupported_constructs") or [])
    got_unsup = set(candidate.get("unsupported_constructs") or [])
    union_unsup = exp_unsup | got_unsup
    pp_block_verified = False
    if union_unsup:
        unverified.append("unsupported_preprocessor_or_macro:" + ",".join(sorted(union_unsup)))
        pp_block_verified = True
        exp_pp_fp = (expected.get("preprocessor") or {}).get("preprocessor_fingerprint")
        got_pp_fp = (candidate.get("preprocessor") or {}).get("preprocessor_fingerprint")
        if exp_pp_fp != got_pp_fp:
            mismatches.append("preprocessor_fingerprint_mismatch")

    strong_body = (
        body_matches > 0 and body_matches == len(required_bodies) and len(required_bodies) > 0
    )
    strong_ast = ast_required == 0 or ast_ok == ast_required
    sets_ok = (
        got_entries == exp_entries
        and got_reach == exp_reach
        and exp_helpers == got_helpers
    )
    verified = (
        strong_body
        and strong_ast
        and sets_ok
        and len(mismatches) == 0
        and not pp_block_verified
    )

    if not required_bodies:
        status = "UNVERIFIED"
        structural_ok = False
        unverified.append("no_reachable_bodies_to_compare")
    elif pp_block_verified:
        # Unsupported macros/includes/ifdef -> fail closed as UNVERIFIED (not VERIFIED).
        status = "UNVERIFIED"
        structural_ok = False
    elif verified:
        status = "VERIFIED"
        structural_ok = True
    elif mismatches:
        status = "MISMATCH"
        structural_ok = False
    else:
        status = "UNVERIFIED"
        structural_ok = False

    equivalence = (
        "EXECUTABLE_STRUCTURE_VERIFIED_SUBSET"
        if structural_ok
        else ("UNVERIFIED" if status == "UNVERIFIED" else "UNPROVEN_OR_MISMATCH")
    )

    return {
        "matches": matches,
        "mismatches": mismatches,
        "unverified": unverified,
        "structural_properties_match": structural_ok,
        "structural_verification": status,
        "equivalence_claim": equivalence,
        "l3_means": (
            "Supported-subset executable structure verified  -  NOT full semantic equivalence."
        ),
        "l3_requires": [
            "entry_handler_set_equality",
            "reachable_set_equality",
            "reachable_body_fingerprint_match",
            "expression_ast_match_when_present",
            "comments_and_strings_excluded",
            "dead_helpers_insufficient",
            "no_uninterpreted_macros_includes_ifdef",
        ],
        "evidence_dimension": "L3_structure_subset",
        "note": (
            "Subset executable analyzer only. Unexpected entry handlers or reachable "
            "helpers prevent VERIFIED. Operator/literal overlap is never sufficient for L3. "
            "Exact semantic equivalence is not claimed."
        ),
    }
