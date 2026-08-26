"""
Full Red↔Blue Loop — run end-to-end in one command.

  KB → Red Team → Sandbox → Evidence Buffer → Harden v3 → Swap → Evaluate → Verify

Usage:
  python src/scripts/run_full_loop.py
  python src/scripts/run_full_loop.py --families 5 --iterations 2
  python src/scripts/run_full_loop.py --skip-train-v1   # if v1 already exists
  python src/scripts/run_full_loop.py --no-swap          # train v2 but keep v1 active

For UI + scheduler, use the Command Center:
  uvicorn backend.api.main:app --app-dir src --reload
  Open http://localhost:8000
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("USE_KB_API", "false")
os.environ.setdefault("EVIDENCE_BUFFER_ENABLED", "true")
os.environ.setdefault("FRAUDSHIELD_ENABLED", "true")
os.environ.setdefault("EVIDENCE_BUFFER_PATH", "data/adversarial_buffer/evidence.jsonl")


def sep(title: str, char: str = "=", width: int = 72):
    print(f"\n{char * width}\n{title}\n{char * width}")


def main():
    parser = argparse.ArgumentParser(description="Run full Red↔Blue loop")
    parser.add_argument("--families", type=int, default=5, help="Simulatable KB families to attack")
    parser.add_argument("--iterations", type=int, default=1, help="Reserved for graph iterations")
    parser.add_argument("--skip-train-v1", action="store_true", help="Skip v1 training if exists")
    parser.add_argument("--no-swap", action="store_true", help="Train v3 but keep prior active model")
    parser.add_argument("--fresh-buffer", action="store_true", default=True, help="Clear buffer before run")
    args = parser.parse_args()

    from backend.platform.loop_runner import LoopRunner, LoopRunConfig

    print("=" * 72)
    print("FULL RED <-> BLUE LOOP")
    print("  KB -> Red Team -> Sandbox -> Buffer -> Harden v3 -> Evaluate -> Swap -> Verify")
    print("=" * 72)

    sep("STEP 1 / 7 — KNOWLEDGE BASE")
    runner = LoopRunner()
    kb = runner._step_kb()
    print(f"  Families:    {kb['total_families']}")
    print(f"  Signals:     {kb['total_signals']}")
    print(f"  Stages:      {kb['total_stages']}")
    print(f"  Simulatable: {kb['simulatable_families']}")

    result = runner.run(
        LoopRunConfig(
            families=args.families,
            skip_train_v1=args.skip_train_v1,
            swap_model=not args.no_swap,
            fresh_buffer=args.fresh_buffer,
            trigger="cli",
        )
    )

    if result.error:
        print(f"\nLOOP FAILED: {result.error}")
        sys.exit(1)

    sep("LOOP COMPLETE")
    print(f"  Run ID:      {result.run_id}")
    print(f"  Buffer:      {result.buffer_stats.get('payment_records', 0)} payments")
    print(f"  Score lift:  {result.comparison.get('buffer_score_lift', 0):+.4f} (v1->v3)")
    ev = result.evaluation
    if ev:
        print(f"  Evaluation:  {ev.get('report_path', '')}")
        print(f"  Integrity:   {ev.get('summary', {}).get('integrity_score', '?')}")
        print(f"  Holdout AUC: {ev.get('detection', {}).get('holdout_pr_auc', 0):.4f}")
        asr = ev.get("asr", {})
        print(f"  ASR (ML):    {asr.get('before_ml_asr', 0):.4f} -> {asr.get('after_ml_asr', 0):.4f}")
    print(f"  Verify:      {result.verify.get('decision')} (ml={result.verify.get('ml_score')}, v={result.verify.get('model_version')})")
    print("\n  Dashboard: uvicorn backend.api.main:app --app-dir src --reload")


if __name__ == "__main__":
    main()
