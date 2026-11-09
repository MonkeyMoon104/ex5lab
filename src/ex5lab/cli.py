"""Command-line interface for ex5lab."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ex5lab import __version__
from ex5lab.binary.compare import compare_binaries
from ex5lab.binary.inspect import inspect_file
from ex5lab.binary.validation import BinaryValidationError, DEFAULT_MAX_BYTES

DISCLAIMER = (
    "ex5lab does not currently perform complete EX5-to-MQ5 decompilation. "
    "Inspect/analyze recover header and metadata observations only unless an "
    "executable decoding rule is independently verified."
)


def _print_human_inspect(report: dict[str, Any]) -> None:
    print(f"path:        {report['path']}")
    print(f"size_bytes:  {report['size_bytes']}")
    print(f"sha256:      {report['sha256']}")
    print(f"ext_is_ex5:  {report['extension_is_ex5']}  (filename heuristic only)")
    ent = report["shannon_entropy"]
    print(
        f"entropy:     {ent['bits_per_byte']} bits/byte "
        f"(normalized={ent['normalized']})"
    )
    print(f"entropy_note:{ent['interpretation']}")
    print(f"unique_bytes:{report['byte_frequency']['unique_bytes']}")
    print("most_common:", report["byte_frequency"]["most_common"][:8])
    magic = report["magic_prefix"]
    print(f"prefix_hex:  {magic['prefix_hex']}")
    print(f"prefix_warn: {magic['warning']}")
    strings = report["printable_strings"]
    print(
        f"strings:     {strings['count']} "
        f"(min_len={strings['min_length']}, truncated={strings['truncated']})"
    )
    for item in strings["strings"][:8]:
        print(f"  @{item['offset']}: {item['value']!r}")
    wide = report.get("utf16le_strings", {})
    print(
        f"utf16le:     {wide.get('count', 0)} "
        f"(truncated={wide.get('truncated')})"
    )
    for item in wide.get("strings", [])[:12]:
        print(f"  @{item['offset']}: {item['value']!r}")
    print("hex head:")
    for row in report["hex_preview"]["head"][:4]:
        print(f"  {row['offset']:08x}  {row['hex']:<48}  {row['ascii']}")
    print(report["research_disclaimer"])


def _print_human_compare(report: dict[str, Any]) -> None:
    print(f"a: {report['a']['path']}  ({report['a']['size_bytes']} bytes)")
    print(f"   sha256={report['a']['sha256']}")
    print(f"b: {report['b']['path']}  ({report['b']['size_bytes']} bytes)")
    print(f"   sha256={report['b']['sha256']}")
    print(f"identical: {report['identical']}")
    metrics = report["metrics"]
    print(
        f"similarity: byte={metrics['byte_similarity']}  "
        f"overlap_eq={metrics['overlap_equal_ratio']}  "
        f"jaccard={metrics['unique_byte_jaccard']}"
    )
    print(
        f"overlap: matching={report['matching_bytes']}  "
        f"differing={report['differing_bytes_in_overlap']}  "
        f"size_delta(b-a)={report['size_delta_b_minus_a']}"
    )
    print(f"common_regions:    {len(report['common_regions'])}")
    print(f"differing_regions: {len(report['differing_regions'])}")
    for region in report["differing_regions"][:10]:
        print(
            f"  diff [{region['start']}..{region['end']}] "
            f"len={region['length']}"
        )
    if report["trailing_size_mismatch"]:
        print(f"trailing: {report['trailing_size_mismatch']}")
    print("sample diffs:")
    for d in report["sample_diff_offsets"][:16]:
        print(f"  @{d['offset']}: {d['a']} -> {d['b']}")
    print(report["research_disclaimer"])


def _write_json(report: dict[str, Any], out: str | None) -> None:
    text = json.dumps(report, indent=2, sort_keys=False)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Wrote JSON report: {out}", file=sys.stderr)
    else:
        print(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ex5lab",
        description=(
            "ex5lab EX5 research toolkit (inspect / compare / analyze). "
            + DISCLAIMER
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"ex5lab {__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="Inspect a binary file")
    p_inspect.add_argument("file", help="Path to file (often .ex5)")
    p_inspect.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    p_inspect.add_argument("--out", help="Write JSON report to this path")
    p_inspect.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    p_inspect.add_argument("--string-min-length", type=int, default=4)
    p_inspect.add_argument("--full-frequency", action="store_true")

    p_compare = sub.add_parser("compare", help="Compare two binary files")
    p_compare.add_argument("first")
    p_compare.add_argument("second")
    p_compare.add_argument("--json", action="store_true")
    p_compare.add_argument("--out")
    p_compare.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)

    p_analyze = sub.add_parser(
        "analyze",
        help="Analyze authorized EX5 input(s) into an output directory",
    )
    p_analyze.add_argument("--input", required=True, help="EX5 file or directory")
    p_analyze.add_argument("--output", required=True, help="Output directory root")

    p_recon = sub.add_parser(
        "reconstruct-ir",
        help="Generate MQ5 from a synthetic ProgramIR JSON fixture (not EX5 decode)",
    )
    p_recon.add_argument("--fixture", required=True, help="ProgramIR JSON fixture")
    p_recon.add_argument("--out", required=True, help="Output .mq5 path")

    p_bench = sub.add_parser(
        "benchmark",
        help="Score a frozen analysis case against a local source oracle directory",
    )
    p_bench.add_argument("--case", required=True, help="Case id or path to case output dir")
    p_bench.add_argument("--oracle", required=True, help="Path to local oracle MQ5 directory")
    p_bench.add_argument("--output", required=True, help="Directory containing frozen case output")
    p_bench.add_argument("--ex5", help="Optional expected EX5 path for SHA verification")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect":
            report = inspect_file(
                args.file,
                max_bytes=args.max_bytes,
                string_min_length=args.string_min_length,
                include_full_frequency=args.full_frequency,
            )
            if args.json or args.out:
                _write_json(report, args.out)
            else:
                _print_human_inspect(report)
            return 0

        if args.command == "compare":
            report = compare_binaries(args.first, args.second, max_bytes=args.max_bytes)
            if args.json or args.out:
                _write_json(report, args.out)
            else:
                _print_human_compare(report)
            return 0

        if args.command == "analyze":
            from ex5lab.pipeline.analyze import analyze_batch

            result = analyze_batch(args.input, args.output)
            print(json.dumps(result, indent=2))
            print(DISCLAIMER, file=sys.stderr)
            return 0 if result.get("ok") or result.get("succeeded", 0) > 0 else 2

        if args.command == "reconstruct-ir":
            from ex5lab.reconstruction.mql5_generator import load_fixture, write_mql5

            program = load_fixture(args.fixture)
            out_path = write_mql5(program, args.out)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "out": str(out_path),
                        "evidence_status": program.provenance.evidence_status,
                        "origin_label": program.origin_label,
                        "disclaimer": (
                            "Generated from ProgramIR fixture only; "
                            "not EX5 opcode decode."
                        ),
                    },
                    indent=2,
                )
            )
            print(DISCLAIMER, file=sys.stderr)
            return 0

        if args.command == "benchmark":
            from ex5lab.benchmark.scorer import score_case

            out_root = Path(args.output)
            case = args.case
            case_dir = Path(case)
            if not case_dir.is_dir():
                matches = sorted(out_root.glob(f"*{case}*"))
                case_dir = matches[0] if matches else (out_root / case)
            freeze = case_dir / "freeze_manifest.json"
            if not freeze.is_file():
                print(f"error: freeze_manifest.json not found under {case_dir}", file=sys.stderr)
                return 2
            report = score_case(
                freeze_manifest_path=freeze,
                oracle_dir=Path(args.oracle),
                case_id=None,
                expected_ex5_path=Path(args.ex5) if args.ex5 else None,
            )
            score_path = case_dir / "benchmark_score.json"
            score_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
            print(f"Wrote {score_path}", file=sys.stderr)
            return 0

    except BinaryValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
