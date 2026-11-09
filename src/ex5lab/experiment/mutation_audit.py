"""Single-site source mutation validation for controlled differentials.

Rejects pairs that differ outside declared allowed mutation sites (byte ranges
or exact replacement pairs). Labels live in external manifests only.
"""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MutationSite:
    """Inclusive start / exclusive end offsets into the baseline source bytes."""

    start: int
    end: int
    label: str = ""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def differing_byte_ranges(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """Return merged half-open ranges where a and b differ (after min-length pad)."""
    n = max(len(a), len(b))
    aa = a + b"\x00" * (n - len(a))
    bb = b + b"\x00" * (n - len(b))
    ranges: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if aa[i] == bb[i]:
            i += 1
            continue
        j = i + 1
        while j < n and aa[j] != bb[j]:
            j += 1
        ranges.append((i, j))
        i = j
    # If lengths differ, the padding region after min(len) is a real length delta;
    # report the trailing exclusive range on the longer file.
    if len(a) != len(b):
        lo = min(len(a), len(b))
        hi = max(len(a), len(b))
        if not ranges or ranges[-1][1] < hi:
            # merge with last if overlapping/adjacent
            if ranges and ranges[-1][1] >= lo:
                ranges[-1] = (ranges[-1][0], hi)
            else:
                ranges.append((lo, hi))
    return ranges


def ranges_covered_by_sites(
    diff_ranges: list[tuple[int, int]], sites: list[MutationSite]
) -> bool:
    if not diff_ranges:
        return True
    if not sites:
        return False

    def covered(start: int, end: int) -> bool:
        for s in sites:
            if start >= s.start and end <= s.end:
                return True
        return False

    return all(covered(a, b) for a, b in diff_ranges)


def audit_pair(
    baseline: bytes,
    variant: bytes,
    *,
    allowed_sites: list[MutationSite] | None = None,
    allowed_replacements: list[tuple[bytes, bytes]] | None = None,
    require_equal_length: bool = False,
    pair_id: str = "",
) -> dict[str, Any]:
    """Validate that variant differs from baseline only at allowed sites.

    If ``allowed_replacements`` is provided, also require that applying exactly
    one of the (old->new) replacements to baseline yields variant.
    """
    diffs = differing_byte_ranges(baseline, variant)
    readable = "\n".join(
        difflib.unified_diff(
            baseline.decode("utf-8", errors="replace").splitlines(),
            variant.decode("utf-8", errors="replace").splitlines(),
            fromfile="baseline",
            tofile="variant",
            lineterm="",
        )
    )
    equal_len = len(baseline) == len(variant)
    sites = allowed_sites or []
    site_ok = ranges_covered_by_sites(diffs, sites) if sites else (len(diffs) == 0)

    replacement_ok: bool | None = None
    matched_replacement: str | None = None
    if allowed_replacements is not None:
        replacement_ok = False
        for old, new in allowed_replacements:
            if old not in baseline:
                continue
            # Exactly one occurrence preferred for controlled experiments.
            if baseline.count(old) != 1:
                continue
            candidate = baseline.replace(old, new, 1)
            if candidate == variant:
                replacement_ok = True
                matched_replacement = f"{old!r} -> {new!r}"
                break

    accepted = True
    reasons: list[str] = []
    if require_equal_length and not equal_len:
        accepted = False
        reasons.append("unequal_source_length")
    if allowed_replacements is not None and not replacement_ok:
        accepted = False
        reasons.append("replacement_not_matched")
    if sites and not site_ok:
        accepted = False
        reasons.append("diff_outside_allowed_sites")
    if not sites and allowed_replacements is None and diffs:
        # No constraint declared -> reject any difference for safety in controlled mode.
        accepted = False
        reasons.append("no_allowed_sites_declared_but_differs")

    return {
        "schema": "phase11_mutation_audit_v1",
        "pair_id": pair_id,
        "accepted": accepted,
        "reject_reasons": reasons,
        "baseline_sha256": sha256_bytes(baseline),
        "variant_sha256": sha256_bytes(variant),
        "baseline_len": len(baseline),
        "variant_len": len(variant),
        "equal_length": equal_len,
        "diff_ranges": [{"start": a, "end": b} for a, b in diffs],
        "allowed_sites": [asdict(s) for s in sites],
        "site_coverage_ok": site_ok,
        "replacement_ok": replacement_ok,
        "matched_replacement": matched_replacement,
        "unified_diff": readable,
    }
