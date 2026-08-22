"""
Full Red↔Blue Loop — run end-to-end in one command.

  KB → Red Team → Sandbox → Evidence Buffer → Harden v2 → Swap → Verify

Usage:
  python src/scripts/run_full_loop.py
  python src/scripts/run_full_loop.py --families 5 --iterations 2
  python src/scripts/run_full_loop.py --skip-train-v1   # if v1 already exists
  python src/scripts/run_full_loop.py --no-swap          # train v2 but keep v1 active
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Defaults for reproducible rule-based loop (no LLM API needed)
os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("USE_KB_API", "false")
os.environ.setdefault("EVIDENCE_BUFFER_ENABLED", "true")
os.environ.setdefault("FRAUDSHIELD_ENABLED", "true")
os.environ.setdefault("EVIDENCE_BUFFER_PATH", "data/adversarial_buffer/evidence.jsonl")


def sep(title: str, char: str = "=", width: int = 72):
    print(f"\n{char * width}\n{title}\n{char * width}")


def step_kb():
    sep("STEP 1 / 7 — KNOWLEDGE BASE")
    from backend.red_team.agent_helpers import OfflineKnowledge
    kb = OfflineKnowledge()
    stats = kb.kb_stats()
    print(f"  Families:    {stats['total_families']}")
    print(f"  Signals:     {stats['total_signals']}")
    print(f"  Stages:      {stats['total_stages']}")
    print(f"  Simulatable: {stats['simulatable_families']}")
    return kb


def step_train_v1(skip: bool):
    sep("STEP 2 / 7 — TRAIN FRAUDSHIELD v1 (baseline)")
    spec = "data/models/features.json"
    if skip and os.path.exists(spec):
        print(f"  Skipped — {spec} already exists")
        return
    print("  Training v1 from master_dataset.json (may take ~1 min)...")
    import subprocess
    r = subprocess.run([sys.executable, "src/scripts/train_model.py"], cwd=os.getcwd())
    if r.returncode != 0:
        sys.exit(r.returncode)
    print("  v1 saved to data/models/")


def step_red_team(families: int, iterations: int, fresh_buffer: bool):
    sep("STEP 3 / 7 — RED TEAM → SANDBOX (Loop A)")
    from backend.red_team.agent_helpers import OfflineKnowledge
    from backend.red_team.agents.threat_hunter import ThreatHunter
    from backend.red_team.agents.attack_planner import AttackPlanner
    from backend.red_team.agents.attack_generator import AttackGenerator
    from backend.red_team.agents.failure_analyzer import FailureAnalyzer
    from backend.red_team.sandbox_client import SandboxClient
    from backend.blue_team.collector import EvidenceCollector
    from backend.blue_team.evidence_buffer import EvidenceBuffer

    buffer_path = os.environ["EVIDENCE_BUFFER_PATH"]
    if fresh_buffer and os.path.exists(buffer_path):
        os.remove(buffer_path)
        print(f"  Cleared buffer: {buffer_path}")

    buffer = EvidenceBuffer(buffer_path)
    collector = EvidenceCollector(buffer=buffer)
    client = SandboxClient()
    kb = OfflineKnowledge()

    simulatable = kb.get_simulatable_families()[:families]
    hunter = ThreatHunter()
    planner = AttackPlanner()
    generator = AttackGenerator()
    analyzer = FailureAnalyzer()

    total_payments = 0
    for i, family in enumerate(simulatable, 1):
        print(f"\n  Campaign {i}/{len(simulatable)}: {family['attack_id']} — {family['name'][:50]}")
        hypothesis = hunter.hypothesis_from_family(family)
        plan = planner.plan(hypothesis)
        sequence = generator.generate_sequence(plan)

        for payload in sequence.payloads:
            response = client.execute_payload(payload.model_dump())
            analysis = analyzer.analyze(response, payload, plan)
            record = collector.collect(
                response, payload, plan, hypothesis, analysis, client.get_sandbox()
            )
            if record:
                total_payments += 1
                print(f"    payment step {record.step}: {record.sandbox_decision} "
                      f"({record.evasion_outcome}) ml={record.ml_score}")

    stats = buffer.stats()
    print(f"\n  Red Team complete: {total_payments} payments → buffer")
    print(f"  Buffer: {stats['payment_records']} payments, {stats['bypassed']} bypassed, "
          f"{stats['blocked']} blocked/challenged")
    print(f"  Families: {', '.join(stats['families'])}")
    return stats


def step_harden(swap: bool):
    sep("STEP 4 / 7 — LOOP B: TRAIN FRAUDSHIELD v2")
    from backend.blue_team.trainer import HardeningTrainer
    from backend.blue_team.evaluator import HardeningEvaluator

    trainer = HardeningTrainer()
    report = trainer.train_v2(n_baseline_legit=4000, n_baseline_fraud=4000)
    print(f"  Baseline rows: {report['baseline_sample']}")
    print(f"  Buffer rows:   {report['buffer_rows']}")
    print(f"  Val PR-AUC:    {report['val_pr_auc']:.4f}")
    print(f"  Val ROC-AUC:   {report['val_roc_auc']:.4f}")
    print(f"  Model:         {report['model_path']}")

    sep("STEP 5 / 7 — EVALUATE v1 vs v2", char="-")
    comparison = HardeningEvaluator().full_report()
    print(f"  v1 buffer mean score: {comparison.v1_buffer_mean_score}")
    print(f"  v2 buffer mean score: {comparison.v2_buffer_mean_score}")
    print(f"  Score lift:           {comparison.buffer_score_lift:+.4f}")
    print(f"  v1 baseline recall:   {comparison.v1_baseline_fraud_recall}")
    print(f"  v2 baseline recall:   {comparison.v2_baseline_fraud_recall}")
    print(f"  Recommend swap:       {comparison.recommend_swap}")

    if swap:
        sep("STEP 6 / 7 — SWAP ACTIVE MODEL TO v2", char="-")
        result = trainer.swap_to_v2()
        print(f"  Active:  {result['active_spec']}")
        print(f"  Backup:  {result['v1_backup']}")
    else:
        print("\n  (Skipped swap — v1 still active. Use without --no-swap to promote v2.)")

    return comparison


def step_verify():
    sep("STEP 7 / 7 — VERIFY HARDENED SANDBOX")
    from backend.sandbox import PaymentSandbox
    from backend.blue_team.fraudshield import load_fraudshield

    model = load_fraudshield()
    if model:
        print(f"  Active model: {model.model_type} {model.version} (threshold={model.threshold:.3f})")
    else:
        print("  No active FraudShield model loaded")

    sandbox = PaymentSandbox()
    sandbox.add_customer("C_loop", "Loop Test", "PAN999", "1990-01-01", "City", trust_score=0.55)
    sandbox.add_device("D_loop", "C_loop")

    # Adversarial high-value payment (mule-like)
    result = sandbox.process_transaction({
        "transaction_id": "T_loop_verify",
        "customer_id": "C_loop",
        "device_id": "D_loop",
        "amount": 35000,
        "payment_rail": "upi",
        "authentication_method": "otp",
        "merchant_risk_score": 0.4,
    })

    state = result.get("state", {})
    print(f"\n  Verification payment (₹35,000 adversarial probe):")
    print(f"    Decision:   {result['decision']}")
    print(f"    Reason:     {result['reason']}")
    print(f"    ML score:   {state.get('ml_score')}")
    print(f"    Rule risk:  {state.get('rule_risk')}")
    print(f"    Combined:   {state.get('risk_score')}")
    triggers = state.get("control_triggers") or result.get("control_triggers") or []
    if triggers:
        print(f"    Triggers:   {', '.join(triggers[:5])}")

    journey = result.get("journey", [])
    if journey:
        print(f"    Journey:    {' → '.join(s['step'] for s in journey)}")


def main():
    parser = argparse.ArgumentParser(description="Run full Red↔Blue loop")
    parser.add_argument("--families", type=int, default=5, help="Simulatable KB families to attack")
    parser.add_argument("--iterations", type=int, default=1, help="Reserved for graph iterations")
    parser.add_argument("--skip-train-v1", action="store_true", help="Skip v1 training if exists")
    parser.add_argument("--no-swap", action="store_true", help="Train v2 but keep v1 active")
    parser.add_argument("--fresh-buffer", action="store_true", default=True, help="Clear buffer before run")
    args = parser.parse_args()

    print("=" * 72)
    print("FULL RED ↔ BLUE LOOP")
    print("  KB → Red Team → Sandbox → Buffer → Harden v2 → Swap → Verify")
    print("=" * 72)

    step_kb()
    step_train_v1(skip=args.skip_train_v1)
    step_red_team(families=args.families, iterations=args.iterations, fresh_buffer=args.fresh_buffer)
    step_harden(swap=not args.no_swap)
    step_verify()

    sep("LOOP COMPLETE ✅")
    print("  Next: run again after more Red Team campaigns to iterate Loop B")
    print("  Or: python src/scripts/test_red_team_dynamic_kb.py --families 10")


if __name__ == "__main__":
    main()
