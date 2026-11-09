#!/usr/bin/env python3
"""Read-only Dependabot PR review CLI (never merges or approves).

Author identity is gated strictly: only ``app/dependabot`` or
``dependabot[bot]`` count as Dependabot. A ``dependabot/`` branch prefix
alone is NOT sufficient  -  those PRs are marked UNKNOWN_AUTHOR and excluded
from the Dependabot list.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_REPO = "MonkeyMoon104/ex5lab"

VALID_DEPENDABOT_AUTHORS = frozenset({"app/dependabot", "dependabot[bot]"})

RECOMMENDATIONS = frozenset(
    {
        "HOLD_REBASE_REQUIRED",
        "HOLD_CI_FAILURE",
        "READY_FOR_HUMAN_MERGE",
        "HOLD_COMPATIBILITY_RISK",
        "REJECT_UPDATE",
        "INCONCLUSIVE",
        "UNKNOWN_AUTHOR",
    }
)

# "Bump actions/checkout from 4 to 5" / "Bump pytest from 7.4.0 to 8.0.0"
_BUMP_TITLE_RE = re.compile(
    r"(?i)\bbump\s+(?P<dep>[\w./@-]+)\s+from\s+(?P<old>[\w.*+-]+)\s+to\s+(?P<new>[\w.*+-]+)"
)
_UPDATE_TITLE_RE = re.compile(
    r"(?i)\b(update|bump)\s+(?P<dep>[\w./@-]+)\s+(?:requirement\s+)?(?:from\s+)?(?P<old>[\w.*+-]+)?\s*(?:to|->)\s*(?P<new>[\w.*+-]+)"
)
_DEP_BODY_RE = re.compile(
    r"(?i)(?:updates?|bumps?|dependency)\s+`?(?P<dep>[\w./@-]+)`?\s+"
    r"from\s+(?P<old>[\w.*+-]+)\s+to\s+(?P<new>[\w.*+-]+)"
)
@dataclass
class PRReview:
    number: int
    url: str
    author: str
    dependency: str | None = None
    old_version: str | None = None
    new_version: str | None = None
    changed_files: list[str] = field(default_factory=list)
    base_branch: str = ""
    base_sha: str = ""
    head_sha: str = ""
    head_ref: str = ""
    mergeable: str | None = None
    checks: dict[str, Any] = field(default_factory=dict)
    last_update: str | None = None
    security_notes: list[str] = field(default_factory=list)
    recommendation: str = "INCONCLUSIVE"
    title: str = ""
    is_dependabot: bool = False
    author_gate: str = "REJECTED"


def _gh(args: list[str], repo: str) -> subprocess.CompletedProcess[str]:
    cmd = ["gh", *args]
    if "--repo" not in args and "-R" not in args:
        # Insert --repo after the subcommand group when missing.
        cmd = ["gh", *args[:2], "--repo", repo, *args[2:]] if len(args) >= 2 else ["gh", *args, "--repo", repo]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _gh_json(args: list[str], repo: str) -> Any:
    r = _gh(args, repo)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"gh failed: {' '.join(args)}")
    text = (r.stdout or "").strip()
    if not text:
        return None
    return json.loads(text)


def author_login(pr: dict[str, Any]) -> str:
    author = pr.get("author") or {}
    if isinstance(author, dict):
        return str(author.get("login") or "")
    return str(author or "")


def is_valid_dependabot_author(login: str) -> bool:
    return login in VALID_DEPENDABOT_AUTHORS


def looks_dependabot_branch(ref: str) -> bool:
    return str(ref or "").startswith("dependabot/")


def parse_dependency_versions(
    title: str,
    body: str = "",
    commits: list[dict[str, Any]] | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Return (dependency, old_version, new_version) when parseable."""
    for text in (title, *(c.get("messageHeadline", "") for c in (commits or []))):
        m = _BUMP_TITLE_RE.search(text) or _UPDATE_TITLE_RE.search(text)
        if m:
            return (
                m.group("dep"),
                m.groupdict().get("old"),
                m.groupdict().get("new"),
            )
    if body:
        # Prefer Dependabot updated-dependencies YAML block when present.
        names = re.findall(r"(?im)^-\s*dependency-name:\s*(\S+)", body)
        prevs = re.findall(r"(?im)^-\s*prev(?:ious)?-version:\s*(\S+)", body)
        news = re.findall(r"(?im)^-\s*new-version:\s*(\S+)", body)
        if names:
            return (
                names[0],
                prevs[0] if prevs else None,
                news[0] if news else None,
            )
        m = _DEP_BODY_RE.search(body)
        if m:
            return m.group("dep"), m.group("old"), m.group("new")
    return None, None, None


def _major_of(version: str | None) -> str | None:
    if not version:
        return None
    m = re.match(r"v?(\d+)", version)
    return m.group(1) if m else None


def summarize_checks(raw: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Normalize gh pr checks / statusCheckRollup into pass/fail/pending."""
    items = raw or []
    counts = {"pass": 0, "fail": 0, "pending": 0, "other": 0}
    details: list[dict[str, str]] = []
    for c in items:
        name = str(c.get("name") or c.get("context") or c.get("workflowName") or "?")
        state = str(
            c.get("state")
            or c.get("conclusion")
            or c.get("status")
            or ""
        ).upper()
        bucket = "other"
        if state in {"SUCCESS", "PASS", "PASSED", "COMPLETED"} and (
            str(c.get("conclusion") or "SUCCESS").upper() in {"SUCCESS", "NEUTRAL", "SKIPPED", ""}
        ):
            # statusCheckRollup uses status=COMPLETED + conclusion=
            conclusion = str(c.get("conclusion") or state).upper()
            if conclusion in {"FAILURE", "FAILED", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "ERROR"}:
                bucket = "fail"
            elif conclusion in {"SUCCESS", "NEUTRAL", "SKIPPED", "PASS", "PASSED"}:
                bucket = "pass"
            elif conclusion in {"", "COMPLETED"} and state in {"SUCCESS", "PASS", "PASSED"}:
                bucket = "pass"
            else:
                bucket = "pending" if state in {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED"} else "other"
        elif state in {"FAILURE", "FAILED", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}:
            bucket = "fail"
        elif state in {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING"}:
            bucket = "pending"
        elif state in {"SUCCESS", "PASS", "PASSED", "NEUTRAL", "SKIPPED"}:
            bucket = "pass"
        counts[bucket] = counts.get(bucket, 0) + 1
        details.append({"name": name, "state": state, "bucket": bucket})
    summary = "pass"
    if counts["fail"]:
        summary = "fail"
    elif counts["pending"]:
        summary = "pending"
    elif not items:
        summary = "pending"
    return {"summary": summary, "counts": counts, "details": details}


def recommend(review: PRReview) -> str:
    if not review.is_dependabot:
        return "UNKNOWN_AUTHOR"

    notes = list(review.security_notes)
    mergeable = (review.mergeable or "").upper()
    check_summary = (review.checks or {}).get("summary", "pending")

    if mergeable in {"CONFLICTING", "FALSE"} or str(review.mergeable).lower() in {
        "false",
        "conflicting",
    }:
        return "HOLD_REBASE_REQUIRED"

    if check_summary == "fail":
        return "HOLD_CI_FAILURE"

    files = [f.lower() for f in review.changed_files]
    suspicious = [
        f
        for f in files
        if f.endswith((".ex5", ".ex4", ".pem", ".key"))
        or f.startswith("oracle/")
        or f.startswith("input/")
    ]
    if suspicious:
        notes.append(f"Unexpected paths in Dependabot PR: {suspicious}")
        review.security_notes = notes
        return "REJECT_UPDATE"

    old_maj = _major_of(review.old_version)
    new_maj = _major_of(review.new_version)
    major = bool(old_maj and new_maj and old_maj != new_maj)
    if major:
        notes.append(f"Major version bump {review.old_version} -> {review.new_version}")

    only_workflows = bool(files) and all(
        f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml")) for f in files
    )
    if major and not only_workflows:
        review.security_notes = notes
        return "HOLD_COMPATIBILITY_RISK"

    if check_summary == "pending" or mergeable in {"UNKNOWN", "NULL", ""}:
        review.security_notes = notes
        return "INCONCLUSIVE"

    if check_summary == "pass" and mergeable in {"MERGEABLE", "TRUE"}:
        if major:
            notes.append(
                "CI green after rebase; only workflow YAML touched  -  "
                "READY_FOR_HUMAN_MERGE (human still decides)."
            )
        review.security_notes = notes
        return "READY_FOR_HUMAN_MERGE"

    # mergeable may be null while checks pass
    if check_summary == "pass":
        return "INCONCLUSIVE"

    return "INCONCLUSIVE"


def list_open_prs(repo: str) -> list[dict[str, Any]]:
    data = _gh_json(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,title,author,url,headRefName,baseRefName,createdAt,updatedAt,labels",
        ],
        repo,
    )
    return list(data or [])


def fetch_pr_detail(repo: str, number: int) -> dict[str, Any]:
    data = _gh_json(
        [
            "pr",
            "view",
            str(number),
            "--json",
            "number,title,body,author,url,headRefName,baseRefName,"
            "baseRefOid,headRefOid,mergeable,updatedAt,commits,files,statusCheckRollup",
        ],
        repo,
    )
    if not isinstance(data, dict):
        raise RuntimeError(f"PR #{number} not found or empty response")
    return data


def review_pr(repo: str, pr_summary: dict[str, Any] | None = None, number: int | None = None) -> PRReview:
    n = number if number is not None else int((pr_summary or {})["number"])
    detail = fetch_pr_detail(repo, n)
    login = author_login(detail)
    head_ref = str(detail.get("headRefName") or "")
    valid = is_valid_dependabot_author(login)

    files_raw = detail.get("files") or []
    changed = []
    for f in files_raw:
        if isinstance(f, dict):
            changed.append(str(f.get("path") or f.get("filename") or ""))
        else:
            changed.append(str(f))
    changed = [c for c in changed if c]

    dep, old_v, new_v = parse_dependency_versions(
        str(detail.get("title") or ""),
        str(detail.get("body") or ""),
        list(detail.get("commits") or []),
    )

    checks = summarize_checks(list(detail.get("statusCheckRollup") or []))
    mergeable = detail.get("mergeable")
    if isinstance(mergeable, bool):
        mergeable_s: str | None = "MERGEABLE" if mergeable else "CONFLICTING"
    else:
        mergeable_s = str(mergeable) if mergeable is not None else None

    security_notes: list[str] = []
    if not valid and looks_dependabot_branch(head_ref):
        security_notes.append(
            f"Branch looks Dependabot-like ({head_ref!r}) but author {login!r} "
            f"is not in {sorted(VALID_DEPENDABOT_AUTHORS)}; excluding from Dependabot list."
        )
    elif not valid:
        security_notes.append(f"Author {login!r} is not Dependabot.")

    body = str(detail.get("body") or "")
    if re.search(r"(?i)security|CVE-|GHSA-", body):
        security_notes.append("Body mentions security/CVE/GHSA  -  human should read advisory.")

    review = PRReview(
        number=int(detail["number"]),
        url=str(detail.get("url") or ""),
        author=login,
        dependency=dep,
        old_version=old_v,
        new_version=new_v,
        changed_files=changed,
        base_branch=str(detail.get("baseRefName") or ""),
        base_sha=str(detail.get("baseRefOid") or ""),
        head_sha=str(detail.get("headRefOid") or ""),
        head_ref=head_ref,
        mergeable=mergeable_s,
        checks=checks,
        last_update=str(detail.get("updatedAt") or ""),
        security_notes=security_notes,
        title=str(detail.get("title") or ""),
        is_dependabot=valid,
        author_gate="ACCEPTED" if valid else "REJECTED",
    )
    review.recommendation = recommend(review)
    return review


def list_dependabot_prs(repo: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (genuine_dependabot_summaries, unknown_author_branch_lookalikes)."""
    open_prs = list_open_prs(repo)
    genuine: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for p in open_prs:
        login = author_login(p)
        ref = str(p.get("headRefName") or "")
        if is_valid_dependabot_author(login):
            genuine.append(p)
        elif looks_dependabot_branch(ref):
            unknown.append(
                {
                    **p,
                    "author_gate": "UNKNOWN_AUTHOR",
                    "note": "dependabot-like branch but author not accepted",
                }
            )
    return genuine, unknown


def reviews_to_markdown(repo: str, reviews: list[PRReview], unknown: list[dict[str, Any]] | None = None) -> str:
    lines = [
        f"# Dependabot PR review  -  `{repo}`",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_",
        "",
        "This report is **read-only**. No merges or approvals were performed.",
        "",
        f"Author gate: only `{', '.join(sorted(VALID_DEPENDABOT_AUTHORS))}` accepted.",
        "",
        "| PR | Dependency | Versions | Checks | Mergeable | Recommendation |",
        "|----|------------|----------|--------|-----------|----------------|",
    ]
    for r in reviews:
        ver = ""
        if r.old_version or r.new_version:
            ver = f"{r.old_version or '?'} -> {r.new_version or '?'}"
        lines.append(
            f"| [#{r.number}]({r.url}) | {r.dependency or 'n/a'} | {ver or 'n/a'} | "
            f"{(r.checks or {}).get('summary', 'n/a')} | {r.mergeable or 'n/a'} | "
            f"**{r.recommendation}** |"
        )
    if unknown:
        lines.extend(["", "## Excluded (UNKNOWN_AUTHOR)", ""])
        for u in unknown:
            lines.append(
                f"- #{u.get('number')} author=`{(u.get('author') or {}).get('login', u.get('author'))}` "
                f"branch=`{u.get('headRefName')}`"
            )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read-only Dependabot PR reviewer (never merges/approves).",
    )
    p.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub OWNER/NAME (default: {DEFAULT_REPO})",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="List genuine Dependabot PRs")
    mode.add_argument("--pr", type=int, metavar="N", help="Review one PR by number")
    mode.add_argument("--all", action="store_true", help="Review all Dependabot PRs")
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", default=False, help="JSON to stdout (default)")
    fmt.add_argument("--markdown", action="store_true", help="Markdown report to stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    use_markdown = bool(args.markdown)
    # default output is JSON unless --markdown
    repo = args.repo

    try:
        if args.list:
            genuine, unknown = list_dependabot_prs(repo)
            payload = {
                "repo": repo,
                "schema": "phase9_dependabot_list_v1",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "dependabot_prs": [
                    {
                        "number": p["number"],
                        "title": p.get("title"),
                        "url": p.get("url"),
                        "author": author_login(p),
                        "head_ref": p.get("headRefName"),
                        "updated_at": p.get("updatedAt"),
                    }
                    for p in genuine
                ],
                "excluded_unknown_author": unknown,
                "count": len(genuine),
            }
            if use_markdown:
                lines = [
                    f"# Dependabot PRs  -  `{repo}`",
                    "",
                    f"Count: **{len(genuine)}**",
                    "",
                ]
                for p in genuine:
                    lines.append(f"- [#{p['number']}]({p.get('url')}) {p.get('title')} (`{author_login(p)}`)")
                if unknown:
                    lines.extend(["", "## Excluded UNKNOWN_AUTHOR", ""])
                    for u in unknown:
                        lines.append(f"- #{u.get('number')} `{u.get('headRefName')}`")
                print("\n".join(lines))
            else:
                print(json.dumps(payload, indent=2))
            return 0

        if args.pr is not None:
            review = review_pr(repo, number=args.pr)
            if use_markdown:
                print(reviews_to_markdown(repo, [review]))
            else:
                print(json.dumps({"repo": repo, "review": asdict(review)}, indent=2))
            return 0

        if args.all:
            genuine, unknown = list_dependabot_prs(repo)
            reviews = [review_pr(repo, pr_summary=p) for p in genuine]
            payload = {
                "repo": repo,
                "schema": "phase9_dependabot_review_v1",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "reviews": [asdict(r) for r in reviews],
                "excluded_unknown_author": unknown,
                "note": "Read-only; never merge or approve from this script.",
            }
            if use_markdown:
                print(reviews_to_markdown(repo, reviews, unknown))
            else:
                print(json.dumps(payload, indent=2))
            return 0

    except (RuntimeError, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
