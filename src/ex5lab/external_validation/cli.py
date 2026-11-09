"""CLI for the external EX5 to MQ5 validation harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ex5lab.decoder.availability import DECODER_AVAILABLE
from ex5lab.external_validation.evaluate import evaluate_frozen_challenge
from ex5lab.external_validation.freeze import freeze_candidate
from ex5lab.external_validation.mechanisms import classify_claim_set
from ex5lab.external_validation.workflow import (
    ChallengeStore,
    attach_report,
    prepare_challenge,
    unlock_ground_truth,
)
from ex5lab.policy.static_only import assert_static_reconstruction_context


def main(argv: list[str] | None = None) -> int:
    assert_static_reconstruction_context(uses_strategy_tester=False)
    p = argparse.ArgumentParser(
        description=(
            "External converter validation harness (does not activate ex5lab decoder). "
            f"DECODER_AVAILABLE={DECODER_AVAILABLE}"
        )
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare", help="Stage 1: register EX5 challenge")
    p_prep.add_argument("--store", type=Path, required=True)
    p_prep.add_argument("--ex5", type=Path, required=True)
    p_prep.add_argument("--ground-truth-mq5", type=Path, default=None)
    p_prep.add_argument("--challenge-id", default=None)
    p_prep.add_argument("--synthetic", action="store_true", default=True)
    p_prep.add_argument("--not-synthetic", action="store_true")
    p_prep.add_argument("--converter-protocol-note", default=None)

    p_freeze = sub.add_parser("freeze", help="Stage 2: freeze candidate MQ5")
    p_freeze.add_argument("--store", type=Path, required=True)
    p_freeze.add_argument("--challenge-id", required=True)
    p_freeze.add_argument("--candidate-mq5", type=Path, required=True)
    p_freeze.add_argument("--converter-id", default=None)

    p_eval = sub.add_parser("evaluate", help="Stage 3: unlock + evaluate")
    p_eval.add_argument("--store", type=Path, required=True)
    p_eval.add_argument("--challenge-id", required=True)
    p_eval.add_argument("--converter-id", default=None)
    p_eval.add_argument("--out", type=Path, default=None)

    p_claims = sub.add_parser("classify-claims", help="Classify developer claim categories")
    p_claims.add_argument("--decompile-claim", action="store_true")
    p_claims.add_argument("--mt-api-fetch-claim", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "prepare":
        synthetic = not args.not_synthetic
        man = prepare_challenge(
            args.store,
            args.ex5,
            challenge_id=args.challenge_id,
            seal_ground_truth_mq5=args.ground_truth_mq5,
            synthetic=synthetic,
            protocol_notes=args.converter_protocol_note,
        )
        print(json.dumps(man, indent=2))
        return 0

    if args.cmd == "freeze":
        store = ChallengeStore(args.store, args.challenge_id)
        meta = freeze_candidate(
            store.dir, args.candidate_mq5, converter_id=args.converter_id
        )
        man_path = store.manifest_path
        man = json.loads(man_path.read_text(encoding="utf-8"))
        man["candidate_frozen"] = True
        man_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(meta, indent=2))
        return 0

    if args.cmd == "evaluate":
        store = ChallengeStore(args.store, args.challenge_id)
        unlock_ground_truth(store)
        report = evaluate_frozen_challenge(store, converter_id=args.converter_id)
        path = attach_report(store, report)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"wrote {path}", flush=True)
        return 0 if report.get("ok") else 1

    if args.cmd == "classify-claims":
        out = classify_claim_set(
            claims_genuine_ex5_decompile=args.decompile_claim,
            claims_mt_api_source_fetch=args.mt_api_fetch_claim,
            official_public_api_documented=False,
        )
        print(json.dumps(out, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
