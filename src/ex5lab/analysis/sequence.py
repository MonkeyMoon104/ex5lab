"""EX5 sequence similarity with explicit computational budgets."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ex5lab.binary.validation import validate_and_read

DEFAULT_EXCLUSION = 744
# Naive DP is O(n*m); refuse when n*m exceeds this product.
DEFAULT_MAX_NAIVE_PRODUCT = 2_000_000  # ~2e6 cell updates
DEFAULT_MAX_BYTES_PER_SIDE = 64_000
DEFAULT_MAX_WALL_SECONDS = 30.0


class SequenceResourceLimit(RuntimeError):
    """Comparison refused due to computational budget."""


def _bytes(path: Path, *, exclude_prefix: int = 0) -> bytes:
    data = validate_and_read(path).data
    return data[exclude_prefix:] if exclude_prefix else data


def longest_common_substring_naive(
    a: bytes,
    b: bytes,
    *,
    max_product: int = DEFAULT_MAX_NAIVE_PRODUCT,
    allow_truncate: bool = False,
    max_scan: int | None = None,
) -> dict[str, Any]:
    """Reference O(n*m) LCS length for small fixtures only.

    Never silently truncates unless allow_truncate=True (then status is PARTIAL).
    """
    a_len, b_len = len(a), len(b)
    product = a_len * b_len
    status = "COMPLETE"
    method = "naive_reference"
    if max_scan is not None and (a_len > max_scan or b_len > max_scan):
        if not allow_truncate:
            return {
                "ok": False,
                "length": None,
                "method": method,
                "status": "RESOURCE_LIMIT",
                "error": "input_exceeds_max_scan_without_truncate",
                "a_len": a_len,
                "b_len": b_len,
                "max_scan": max_scan,
                "work_product": product,
            }
        a = a[:max_scan]
        b = b[:max_scan]
        status = "PARTIAL_TRUNCATED"
        product = len(a) * len(b)

    if product > max_product:
        return {
            "ok": False,
            "length": None,
            "method": method,
            "status": "RESOURCE_LIMIT",
            "error": f"naive_product {product} exceeds max_product {max_product}",
            "a_len": a_len,
            "b_len": b_len,
            "work_product": product,
            "max_product": max_product,
        }

    if not a or not b:
        return {
            "ok": True,
            "length": 0,
            "method": method,
            "status": status,
            "a_len": len(a),
            "b_len": len(b),
            "work_product": 0,
        }

    t0 = time.perf_counter()
    prev = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b):
            v = prev[j] + 1 if ca == cb else 0
            cur.append(v)
            if v > best:
                best = v
        prev = cur
    elapsed = time.perf_counter() - t0
    return {
        "ok": True,
        "length": best,
        "method": method,
        "status": status,
        "a_len": len(a),
        "b_len": len(b),
        "work_product": len(a) * len(b),
        "wall_seconds": round(elapsed, 6),
    }


def longest_common_via_suffix(
    a: bytes,
    b: bytes,
    *,
    min_length: int = 8,
    max_bytes_per_side: int = DEFAULT_MAX_BYTES_PER_SIDE,
    max_naive_product: int = DEFAULT_MAX_NAIVE_PRODUCT,
    allow_truncate: bool = False,
) -> dict[str, Any]:
    """Prefer pydivsufsort; fall back to naive only when within budget."""
    a_len, b_len = len(a), len(b)
    if a_len > max_bytes_per_side or b_len > max_bytes_per_side:
        if not allow_truncate:
            return {
                "ok": False,
                "length": None,
                "method": "refused",
                "status": "RESOURCE_LIMIT",
                "error": "input_exceeds_max_bytes_per_side",
                "a_len": a_len,
                "b_len": b_len,
                "max_bytes_per_side": max_bytes_per_side,
            }
        a = a[:max_bytes_per_side]
        b = b[:max_bytes_per_side]
        truncated = True
    else:
        truncated = False

    try:
        import numpy as np
        from pydivsufsort import common_substrings
    except ImportError as exc:
        # Early budget gate - never invoke naive when product exceeds limit.
        # Missing optional research dep is DEPENDENCY_UNAVAILABLE, not a
        # scientific mismatch and not a pure RESOURCE_LIMIT (budget alone).
        product = len(a) * len(b)
        if product > max_naive_product:
            return {
                "ok": False,
                "length": None,
                "method": "refused",
                "status": "DEPENDENCY_UNAVAILABLE",
                "error": f"ImportError_and_naive_refused:{exc}",
                "missing_dependency": "pydivsufsort",
                "a_len": len(a),
                "b_len": len(b),
                "work_product": product,
                "max_naive_product": max_naive_product,
            }
        out = longest_common_substring_naive(a, b, max_product=max_naive_product)
        out["fallback_reason"] = f"ImportError:{exc}"
        out["missing_dependency"] = "pydivsufsort"
        if truncated and out.get("ok"):
            out["status"] = "PARTIAL_TRUNCATED"
        return out

    # int32 avoids uint8 separator overflow when payload contains 0xFF
    s1 = np.frombuffer(a, dtype=np.uint8).astype(np.int32, copy=False)
    s2 = np.frombuffer(b, dtype=np.uint8).astype(np.int32, copy=False)
    t0 = time.perf_counter()
    try:
        res = common_substrings(s1, s2, limit=min_length)
        length = max((int(t[2]) for t in res), default=0) if res else 0
        if length == 0 and min_length > 1:
            res2 = common_substrings(s1, s2, limit=1)
            length = max((int(t[2]) for t in res2), default=0) if res2 else 0
        elapsed = time.perf_counter() - t0
        return {
            "ok": True,
            "length": length,
            "method": "pydivsufsort.common_substrings",
            "status": "PARTIAL_TRUNCATED" if truncated else "COMPLETE",
            "a_len": len(a),
            "b_len": len(b),
            "min_length_param": min_length,
            "wall_seconds": round(elapsed, 6),
            "input_a_len": a_len,
            "input_b_len": b_len,
        }
    except Exception as exc:  # noqa: BLE001 - API failure must not unbounded-fallback
        # Do NOT call naive on large inputs after suffix failure
        product = len(a) * len(b)
        if product <= max_naive_product:
            out = longest_common_substring_naive(a, b, max_product=max_naive_product)
            out["fallback_reason"] = f"suffix_api:{exc}"
            if truncated and out.get("ok"):
                out["status"] = "PARTIAL_TRUNCATED"
            return out
        return {
            "ok": False,
            "length": None,
            "method": "pydivsufsort_failed",
            "status": "RESOURCE_LIMIT",
            "error": f"suffix_api_failed_and_naive_refused:{exc}",
            "a_len": len(a),
            "b_len": len(b),
            "work_product": product,
        }


def tlsh_distance(a: bytes, b: bytes) -> dict[str, Any]:
    try:
        import tlsh
    except ImportError as exc:
        return {"ok": False, "error": f"ImportError:{exc}"}
    if len(a) < 50 or len(b) < 50:
        return {"ok": False, "error": "input too short for TLSH"}
    ha = tlsh.hash(a)
    hb = tlsh.hash(b)
    if ha in ("TNULL", "", None) or hb in ("TNULL", "", None):
        return {"ok": False, "error": "tlsh null hash", "ha": ha, "hb": hb}
    return {"ok": True, "distance": int(tlsh.diff(ha, hb)), "ha": ha, "hb": hb, "method": "tlsh"}


def pairwise_sequence_report(
    paths: list[str | Path],
    *,
    exclude_prefix: int = DEFAULT_EXCLUSION,
    label: str = "set",
    max_bytes_per_side: int = DEFAULT_MAX_BYTES_PER_SIDE,
    max_naive_product: int = DEFAULT_MAX_NAIVE_PRODUCT,
    allow_truncate: bool = False,
) -> dict[str, Any]:
    loaded = [(str(p), _bytes(Path(p), exclude_prefix=exclude_prefix)) for p in paths]
    lcs = []
    tlsh_rows = []
    for i in range(len(loaded)):
        for j in range(i + 1, len(loaded)):
            pa, da = loaded[i]
            pb, db = loaded[j]
            lcs.append(
                {
                    "a": pa,
                    "b": pb,
                    **longest_common_via_suffix(
                        da,
                        db,
                        max_bytes_per_side=max_bytes_per_side,
                        max_naive_product=max_naive_product,
                        allow_truncate=allow_truncate,
                    ),
                }
            )
            tlsh_rows.append({"a": pa, "b": pb, **tlsh_distance(da, db)})
    lcs_ok = [x["length"] for x in lcs if x.get("ok") and x.get("length") is not None]
    tlsh_ok = [x["distance"] for x in tlsh_rows if x.get("ok")]
    any_dep = any(x.get("status") == "DEPENDENCY_UNAVAILABLE" for x in lcs)
    any_limit = any(x.get("status") == "RESOURCE_LIMIT" for x in lcs)
    any_partial = any(x.get("status") == "PARTIAL_TRUNCATED" for x in lcs)
    # Priority: dependency gaps ≠ resource budgets ≠ truncation ≠ complete
    if any_dep:
        completeness = "DEPENDENCY_UNAVAILABLE"
    elif any_limit:
        completeness = "RESOURCE_LIMIT"
    elif any_partial:
        completeness = "PARTIAL"
    else:
        completeness = "COMPLETE"
    return {
        "label": label,
        "n_files": len(paths),
        "exclude_prefix": exclude_prefix,
        "exclusion_note": "heuristic post-header window, not verified payload boundary",
        "completeness": completeness,
        "budgets": {
            "max_bytes_per_side": max_bytes_per_side,
            "max_naive_product": max_naive_product,
            "allow_truncate": allow_truncate,
        },
        "lcs": {
            "pairs": lcs,
            "mean_length": (sum(lcs_ok) / len(lcs_ok)) if lcs_ok else None,
            "min_length": min(lcs_ok) if lcs_ok else None,
            "max_length": max(lcs_ok) if lcs_ok else None,
            "n_ok": len(lcs_ok),
            "n_failed": len(lcs) - len(lcs_ok),
        },
        "tlsh": {
            "pairs": tlsh_rows,
            "mean_distance": (sum(tlsh_ok) / len(tlsh_ok)) if tlsh_ok else None,
            "n_ok": len(tlsh_ok),
        },
    }
