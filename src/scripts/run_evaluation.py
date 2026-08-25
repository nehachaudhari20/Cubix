#!/usr/bin/env python3
"""
Phase 11 — Run full Blue Team evaluation report.

Usage:
  python src/scripts/run_evaluation.py
  python src/scripts/run_evaluation.py --before v1 --after v3
  python src/scripts/run_evaluation.py --output data/models/evaluation_report.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.blue_team.evaluation_runner import EvaluationRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 11 — Full evaluation report")
    parser.add_argument("--before", default="v1", help="Baseline model version")
    parser.add_argument("--after", default="v2", help="Hardened model version")
    parser.add_argument("--baseline-legit", type=int, default=500)
    parser.add_argument("--baseline-fraud", type=int, default=500)
    parser.add_argument(
        "--output",
        default=os.path.join("data", "models", "evaluation_report.json"),
        help="JSON report path",
    )
    args = parser.parse_args()

    runner = EvaluationRunner()
    print("=" * 72)
    print("PHASE 11 — Full Evaluation Report")
    print("=" * 72)
    print(f"  Before: {args.before}  After: {args.after}")

    try:
        report = runner.run(
            before_version=args.before,
            after_version=args.after,
            n_baseline_legit=args.baseline_legit,
            n_baseline_fraud=args.baseline_fraud,
            save_path=args.output,
        )
    except FileNotFoundError as exc:
        print(f"\nERROR: {exc}")
        return 1

    s = report.summary
    print("\n--- Summary ---")
    print(f"  Recommend hardening: {s.get('recommend_hardening')}")
    print(f"  Integrity:           {s.get('integrity_score')} passed")
    print(f"  Holdout PR-AUC:      {s.get('primary_detection_metric', 0):.4f}")
    print(f"  Buffer score lift:   {s.get('buffer_score_lift', 0):.4f}")
    print(f"  ASR ML recall lift:  {s.get('asr_ml_recall_lift', 0):.4f}")
    print(f"  Mean family recall:  {s.get('mean_family_recall', 0):.4f}")
    print(f"  Score separation:    {s.get('score_separation', 0):.4f}")

    print("\n--- Integrity Checks ---")
    for check in report.integrity.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"  [{status}] {check.name}: {check.value:.4f} — {check.detail}")

    print("\n--- ASR ---")
    print(f"  Payment attacks:     {report.asr.payment_attacks}")
    print(f"  Historical bypass:   {report.asr.historical_bypass_rate:.2%}")
    print(f"  Before ML recall:    {report.asr.before_ml_recall:.4f}")
    print(f"  After ML recall:     {report.asr.after_ml_recall:.4f}")
    print(f"  ASR reduction (ML):  {report.asr.asr_reduction:.4f}")

    print(f"\nReport saved: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
