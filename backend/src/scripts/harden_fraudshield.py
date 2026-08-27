"""
Loop B — Batch harden FraudShield from Red Team adversarial buffer.

Usage:
  python src/scripts/harden_fraudshield.py
  python src/scripts/harden_fraudshield.py --v3
  python src/scripts/harden_fraudshield.py --v3 --swap
  python src/scripts/harden_fraudshield.py --evaluate-only
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.blue_team.trainer import HardeningTrainer
from backend.blue_team.evaluator import HardeningEvaluator
from backend.blue_team.evidence_buffer import EvidenceBuffer


def main():
    parser = argparse.ArgumentParser(description="Loop B — Harden FraudShield")
    parser.add_argument("--v2", action="store_true", help="Train v2 LightGBM instead of default v3 stack")
    parser.add_argument("--v3", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--swap", action="store_true", help="Promote trained version to active model")
    parser.add_argument("--evaluate-only", action="store_true", help="Skip training, only compare models")
    parser.add_argument("--baseline-legit", type=int, default=4000)
    parser.add_argument("--baseline-fraud", type=int, default=4000)
    args = parser.parse_args()

    buffer = EvidenceBuffer()
    stats = buffer.stats()

    print("=" * 72)
    print("LOOP B — FraudShield Batch Hardening")
    print("=" * 72)
    use_v3 = not args.v2
    print(f"  Mode: {'v3 stacked' if use_v3 else 'v2 LightGBM'}")
    print(f"  Buffer: {stats['payment_records']} payment records from {len(stats['families'])} families")
    print(f"  Bypassed: {stats['bypassed']}  Blocked/Challenged: {stats['blocked']}")

    trainer = HardeningTrainer()
    evaluator = HardeningEvaluator()

    if not args.evaluate_only:
        if stats["payment_records"] < 1:
            print("\nERROR: Adversarial buffer is empty.")
            print("Run Red Team first: python src/scripts/run_red_team_continuous.py")
            sys.exit(1)

        if use_v3:
            print("\n--- Training FraudShield v3 (stacked ensemble) ---")
            report = trainer.train_v3(
                n_baseline_legit=args.baseline_legit,
                n_baseline_fraud=args.baseline_fraud,
            )
            det = report.get("detection", {})
            mix = report.get("mix_stats", {})
            print(f"  Total rows:    {mix.get('total_rows', '?')}")
            print(f"  Buffer fraud:  {mix.get('buffer_selected_rows', mix.get('buffer_fraud_rows', 0))}")
            print(f"  Hard negatives:{mix.get('hard_negative_rows', 0)}")
            print(f"  Val PR-AUC:    {det.get('pr_auc', 0):.4f}")
            print(f"  Val recall:    {det.get('recall', 0):.4f}")
            print(f"  Train PR-AUC:  {report.get('train_detection', {}).get('pr_auc', 0):.4f}")
            print(f"  Overfit gap:   {report.get('overfit_gap_pr_auc', 0):.4f}")
            mw = report.get("meta_weights", {})
            if mw:
                print(f"  Meta weights:  xgb={mw.get('xgboost', 0):.3f} lgb={mw.get('lightgbm', 0):.3f} log={mw.get('logistic', 0):.3f}")
            print(f"  Threshold@1%FPR:{report.get('threshold_at_1pct_fpr', report.get('decision_threshold', 0)):.4f}")
            print(f"  Artifacts:     {report['artifact_dir']}")
        else:
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

    if use_v3 and not args.evaluate_only:
        v3 = evaluator.load_model_version("v3")
        if v3:
            v3_scores = evaluator._score_buffer_records(v3)
            if v3_scores:
                import numpy as np
                print(f"\n--- v3 buffer mean score: {float(np.mean(v3_scores)):.4f} ---")

    if args.swap:
        if use_v3:
            result = trainer.swap_to_v3()
            label = "v3 stacked"
        else:
            result = trainer.swap_to_v2()
            label = "v2"
        print(f"\n--- Swapped active model to {label} ---")
        for key, val in result.items():
            print(f"  {key}: {val}")

    print("\n" + "=" * 72)
    print("Loop B complete")
    print("=" * 72)


if __name__ == "__main__":
    main()
