"""
Step 5C — Loop B hardening tests.

Run:
  python src/scripts/test_harden_fraudshield.py

Requires:
  - data/models/fraudshield_v1.* (run train_model.py)
  - adversarial buffer populated by test 1
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("FRAUDSHIELD_ENABLED", "false")
os.environ.setdefault("RED_TEAM_USE_LLM", "false")

from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.blue_team.collector import EvidenceCollector
from backend.blue_team.trainer import HardeningTrainer
from backend.blue_team.evaluator import HardeningEvaluator
from backend.blue_team.fraudshield import load_fraudshield
from backend.red_team.sandbox_client import SandboxClient
from backend.red_team.agents.attack_planner import AttackPlanner
from backend.red_team.agents.attack_generator import AttackGenerator
from backend.red_team.agents.failure_analyzer import FailureAnalyzer
from backend.red_team.agents.threat_hunter import ThreatHunter
from backend.red_team.agent_helpers import OfflineKnowledge


MODEL_DIR = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")


def populate_buffer(path: str, min_payments: int = 3) -> int:
    """Run a few KB families through sandbox to fill the buffer."""
    buffer = EvidenceBuffer(path)
    collector = EvidenceCollector(buffer=buffer)
    client = SandboxClient()
    kb = OfflineKnowledge()

    stored = 0
    for family_id in ["CM-001", "AUT-001", "AML-001"]:
        family = kb.get_family(family_id)
        if not family:
            continue
        hypothesis = ThreatHunter().hypothesis_from_family(family)
        plan = AttackPlanner().plan(hypothesis)
        sequence = AttackGenerator().generate_sequence(plan)
        analyzer = FailureAnalyzer()

        for payload in sequence.payloads:
            response = client.execute_payload(payload.model_dump())
            analysis = analyzer.analyze(response, payload, plan)
            record = collector.collect(response, payload, plan, hypothesis, analysis, client.get_sandbox())
            if record:
                stored += 1
        if stored >= min_payments:
            break
    return stored


def test_train_v2():
    print("\n" + "=" * 60)
    print("TEST 1: HardeningTrainer — train FraudShield v2")
    print("=" * 60)

    v1 = load_fraudshield(MODEL_DIR)
    if v1 is None:
        print("  ⚠️  v1 model not found — run: python src/scripts/train_model.py")
        print("  SKIPPED")
        return False

    with tempfile.TemporaryDirectory() as tmp:
        buffer_path = os.path.join(tmp, "evidence.jsonl")
        populate_buffer(buffer_path, min_payments=3)

        trainer = HardeningTrainer(model_dir=MODEL_DIR, buffer_path=buffer_path)
        report = trainer.train_v2(n_baseline_legit=500, n_baseline_fraud=500)

        assert os.path.exists(report["model_path"])
        assert os.path.exists(report["spec_path"])
        print(f"  Trained v2: PR-AUC={report['val_pr_auc']:.4f}")
        print(f"  Buffer rows used: {report['buffer_rows']}")
        print("  ✅ PASSED")
        return True


def test_evaluate_and_swap():
    print("\n" + "=" * 60)
    print("TEST 2: HardeningEvaluator — v1 vs v2 comparison")
    print("=" * 60)

    v1_spec = os.path.join(MODEL_DIR, "features.json")
    v2_spec = os.path.join(MODEL_DIR, "features_v2.json")
    if not os.path.exists(v1_spec) or not os.path.exists(v2_spec):
        print("  SKIPPED (run test 1 first or harden_fraudshield.py)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        buffer_path = os.path.join(tmp, "evidence.jsonl")
        populate_buffer(buffer_path)

        evaluator = HardeningEvaluator(model_dir=MODEL_DIR, buffer_path=buffer_path)
        report = evaluator.full_report()

        print(f"  Buffer lift: {report.buffer_score_lift:+.4f}")
        print(f"  v1 buffer mean: {report.v1_buffer_mean_score}")
        print(f"  v2 buffer mean: {report.v2_buffer_mean_score}")
        print(f"  Recommend swap: {report.recommend_swap}")
        assert report.buffer_records >= 1
        print("  ✅ PASSED")


def test_full_loop_b_cli():
    print("\n" + "=" * 60)
    print("TEST 3: Full Loop B pipeline")
    print("=" * 60)

    v1 = load_fraudshield(MODEL_DIR)
    if v1 is None:
        print("  SKIPPED (no v1 model)")
        return

    default_buffer = os.path.join("data", "adversarial_buffer", "evidence.jsonl")
    os.makedirs(os.path.dirname(default_buffer), exist_ok=True)

    # Ensure buffer has data
    if not os.path.exists(default_buffer) or os.path.getsize(default_buffer) == 0:
        populate_buffer(default_buffer, min_payments=5)

    trainer = HardeningTrainer()
    if trainer.buffer.stats()["payment_records"] < 1:
        print("  SKIPPED (empty buffer)")
        return

    report = trainer.train_v2(n_baseline_legit=500, n_baseline_fraud=500)
    evaluator = HardeningEvaluator()
    comparison = evaluator.full_report()

    print(f"  v2 val PR-AUC: {report['val_pr_auc']:.4f}")
    print(f"  Buffer score lift: {comparison.buffer_score_lift:+.4f}")
    print("  ✅ PASSED")


def main():
    print("Loop B Hardening Tests (Step 5C)")
    ok = test_train_v2()
    if ok:
        test_evaluate_and_swap()
        test_full_loop_b_cli()
    print("\n" + "=" * 60)
    print("HARDENING TESTS COMPLETE ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
