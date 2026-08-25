#!/usr/bin/env python3
"""Phase 11 (11a-11e): EvaluationRunner and sub-pillar tests."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.blue_team.evaluation.asr import run_asr_for_loop
from backend.blue_team.evaluation.detection import run_detection_suite
from backend.blue_team.evaluation.fidelity import run_fidelity_checks
from backend.blue_team.evaluation.generalization import run_generalization_suite
from backend.blue_team.evaluation.integrity import run_integrity_battery
from backend.blue_team.evaluation.manifest import load_training_manifest
from backend.blue_team.evaluation.context import EvaluationContext
from backend.blue_team.evaluation_runner import EvaluationRunner
from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.blue_team.schemas import EvidenceRecord


def _record(
    eid: str,
    family: str = "CM-001",
    decision: str = "BLOCK",
    *,
    campaign: str = "camp-test",
    variant: str = "v1",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=eid,
        campaign_id=campaign,
        attack_family=family,
        attack_variant=variant,
        action_type="initiate_payment",
        sandbox_decision=decision,
        evasion_outcome="bypassed" if decision == "ALLOW" else "blocked",
        ml_score=0.3,
        label=1,
        features={"amount": 5000, "payment_rail": "upi", "hour_of_day": 14},
        timestamp="2026-08-01T00:00:00Z",
    )


def test_11a_detection_slices():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features.json")):
        print("SKIP 11a: no v1")
        return
    with tempfile.TemporaryDirectory() as tmp:
        buffer = EvidenceBuffer(os.path.join(tmp, "evidence.jsonl"))
        buffer.append(_record("e1", "AML-001"))
        runner = EvaluationRunner(model_dir=model_dir, buffer_path=buffer.path)
        try:
            ctx = EvaluationContext.build(runner.evaluator, runner.model_dir, "v1", "v2")
        except FileNotFoundError:
            print("SKIP 11a: v2 missing")
            return
        det = run_detection_suite(ctx, n_baseline_legit=100, n_baseline_fraud=100)
        assert det.holdout.get("before")
        assert det.test.get("rows", 0) > 0
        assert len(det.suite_table) >= 4
        print(f"11a detection: holdout={det.after_holdout_pr_auc:.4f} test_rows={det.test.get('rows')}")


def test_11b_fidelity_checks():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features_v2.json")):
        print("SKIP 11b: v2 missing")
        return
    with tempfile.TemporaryDirectory() as tmp:
        runner = EvaluationRunner(model_dir=model_dir, buffer_path=os.path.join(tmp, "b.jsonl"))
        ctx = EvaluationContext.build(runner.evaluator, runner.model_dir, "v1", "v2")
        fid = run_fidelity_checks(ctx, n_baseline_legit=200, n_baseline_fraud=200)
        assert fid.legit_samples > 0
        assert len(fid.checks) >= 4
        print(f"11b fidelity: separation={fid.score_separation:.4f} checks={len(fid.checks)}")


def test_11c_generalization_lofo():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features.json")):
        print("SKIP 11c")
        return
    with tempfile.TemporaryDirectory() as tmp:
        buffer = EvidenceBuffer(os.path.join(tmp, "evidence.jsonl"))
        buffer.append(_record("e1", "AML-001", campaign="c1", variant="var_a"))
        buffer.append(_record("e2", "AML-002", "ALLOW", campaign="c2", variant="var_b"))
        buffer.append(_record("e3", "CM-001", campaign="c2"))
        runner = EvaluationRunner(model_dir=model_dir, buffer_path=buffer.path)
        try:
            ctx = EvaluationContext.build(runner.evaluator, runner.model_dir, "v1", "v2")
        except FileNotFoundError:
            print("SKIP 11c: v2 missing")
            return
        gen = run_generalization_suite(ctx)
        assert len(gen.family_recall) == 3
        assert len(gen.lofo) == 3
        assert len(gen.variant_recall) >= 2
        assert gen.composite_campaign_count >= 1
        print(f"11c generalization: families={len(gen.family_recall)} lofo={len(gen.lofo)} composite={gen.composite_campaign_count}")


def test_11d_integrity_battery():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features_v2.json")):
        print("SKIP 11d")
        return
    with tempfile.TemporaryDirectory() as tmp:
        runner = EvaluationRunner(model_dir=model_dir, buffer_path=os.path.join(tmp, "b.jsonl"))
        ctx = EvaluationContext.build(runner.evaluator, runner.model_dir, "v1", "v2")
        integrity = run_integrity_battery(ctx, n_baseline_legit=150, n_baseline_fraud=150)
        names = {c.name for c in integrity.checks}
        assert "null_control" in names
        assert "ablation_zero_features" in names
        assert "leakage_proxy" in names
        assert "temporal_split" in names
        print(f"11d integrity: {integrity.passed_count}/{integrity.total_checks}")


def test_11e_asr_loop_helper():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features_v2.json")):
        print("SKIP 11e")
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "evidence.jsonl")
        buffer = EvidenceBuffer(path)
        buffer.append(_record("e1", decision="ALLOW"))
        asr = run_asr_for_loop(model_dir=model_dir, buffer_path=path)
        assert asr["payment_attacks"] == 1
        assert "before_ml_asr" in asr
        assert "after_ml_asr" in asr
        print(f"11e asr: reduction={asr['asr_reduction']:.4f}")


def test_full_runner_smoke():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features.json")):
        print("SKIP full runner")
        return
    with tempfile.TemporaryDirectory() as tmp:
        buffer_path = os.path.join(tmp, "evidence.jsonl")
        buffer = EvidenceBuffer(buffer_path)
        buffer.append(_record("e1", "AML-001", "BLOCK"))
        buffer.append(_record("e2", "AML-002", "ALLOW"))
        out = os.path.join(tmp, "evaluation_report.json")
        runner = EvaluationRunner(model_dir=model_dir, buffer_path=buffer_path)
        try:
            report = runner.run(
                before_version="v1",
                after_version="v2",
                n_baseline_legit=200,
                n_baseline_fraud=200,
                save_path=out,
            )
        except FileNotFoundError:
            print("SKIP full: v2 missing")
            return
        payload = json.load(open(out))
        assert "detection" in payload
        assert payload["detection"]["holdout"]
        assert "11a_detection" in payload["summary"]["pillars"]
        assert report.asr.payment_attacks == 2
        print(f"full report: integrity={report.summary['integrity_score']}")


if __name__ == "__main__":
    test_11a_detection_slices()
    test_11b_fidelity_checks()
    test_11c_generalization_lofo()
    test_11d_integrity_battery()
    test_11e_asr_loop_helper()
    test_full_runner_smoke()
    print("\nAll Phase 11 (11a-11e) tests passed.")
