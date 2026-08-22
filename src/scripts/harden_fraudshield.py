"""
Loop B — Batch harden FraudShield from Red Team adversarial buffer.

Usage:
  python src/scripts/harden_fraudshield.py
  python src/scripts/harden_fraudshield.py --swap
  python src/scripts/harden_fraudshield.py --evaluate-only
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.blue_team.trainer import HardeningTrainer
from backend.blue_team.evaluator import HardeningEvaluator
from backend.blue_team.evidence_buffer import EvidenceBuffer


def main():
    parser = argparse.ArgumentParser(description="Loop B — Harden FraudShield v2")
    parser.add_argument("--swap", action="store_true", help="Promote v2 to active model after training")
    parser.add_argument("--evaluate-only", action="store_true", help="Skip training, only compare v1 vs v2")
    parser.add_argument("--baseline-legit", type=int, default=4000)
    parser.add_argument("--baseline-fraud", type=int, default=4000)
    args = parser.parse_args()

    buffer = EvidenceBuffer()
    stats = buffer.stats()

    print("=" * 72)
    print("LOOP B — FraudShield Batch Hardening")
    print("=" * 72)
    print(f"  Buffer: {stats['payment_records']} payment records from {len(stats['families'])} families")
    print(f"  Bypassed: {stats['bypassed']}  Blocked/Challenged: {stats['blocked']}")

    trainer = HardeningTrainer()
    evaluator = HardeningEvaluator()

    if not args.evaluate_only:
        if stats["payment_records"] < 1:
            print("\nERROR: Adversarial buffer is empty.")
            print("Run Red Team first: python src/scripts/test_evidence_buffer.py")
            sys.exit(1)

        print("\n--- Training FraudShield v2 ---")
        report = trainer.train_v2(
            n_baseline_legit=args.baseline_legit,
            n_baseline_fraud=args.baseline_fraud,
        )
        print(f"  Baseline rows: {report['baseline_sample']}")
        print(f"  Buffer rows:   {report['buffer_rows']}")
        print(f"  Val PR-AUC:    {report['val_pr_auc']:.4f}")
        print(f"  Val ROC-AUC:   {report['val_roc_auc']:.4f}")
        print(f"  Threshold:     {report['decision_threshold']:.4f}")
        print(f"  Saved:         {report['model_path']}")

    print("\n--- Evaluating v1 vs v2 ---")
    try:
        hardening = evaluator.full_report()
    except FileNotFoundError as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)

    print(f"  Buffer records:     {hardening.buffer_records}")
    print(f"  v1 mean score:      {hardening.v1_buffer_mean_score}")
    print(f"  v2 mean score:      {hardening.v2_buffer_mean_score}")
    print(f"  Score lift:         {hardening.buffer_score_lift:+.4f}")
    print(f"  v1 baseline recall: {hardening.v1_baseline_fraud_recall}")
    print(f"  v2 baseline recall: {hardening.v2_baseline_fraud_recall}")
    print(f"  Bypassed attacks:   {hardening.bypassed_attacks}")
    print(f"  Recommend swap:     {hardening.recommend_swap}")

    if args.swap:
        result = trainer.swap_to_v2()
        print("\n--- Swapped active model to v2 ---")
        print(f"  Active spec: {result['active_spec']}")
        print(f"  v1 backup:   {result['v1_backup']}")

    print("\n" + "=" * 72)
    print("Loop B complete")
    print("=" * 72)


if __name__ == "__main__":
    main()
