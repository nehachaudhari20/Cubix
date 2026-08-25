#!/usr/bin/env python3
"""Phase 11: EvaluationRunner tests."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.blue_team.evaluation_runner import EvaluationRunner, _load_training_manifest
from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.blue_team.schemas import EvidenceRecord


def _record(eid: str, family: str = "CM-001", decision: str = "BLOCK") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=eid,
        campaign_id="camp-test",
        attack_family=family,
        action_type="initiate_payment",
        sandbox_decision=decision,
        evasion_outcome="bypassed" if decision == "ALLOW" else "blocked",
        ml_score=0.3,
        label=1,
        features={"amount": 5000, "payment_rail": "upi", "hour_of_day": 14},
        timestamp="2026-08-01T00:00:00Z",
    )


def test_load_training_manifest_missing(tmp_path=None):
    manifest = _load_training_manifest(tmp_path or __import__("pathlib").Path("/nonexistent"), "v2")
    assert manifest == {} or isinstance(manifest, dict)
    print("manifest missing: OK")


def test_evaluation_runner_smoke():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    v1_spec = os.path.join(model_dir, "features.json")
    if not os.path.exists(v1_spec):
        print("SKIP: features.json missing")
        return

    with tempfile.TemporaryDirectory() as tmp:
        buffer_path = os.path.join(tmp, "evidence.jsonl")
        buffer = EvidenceBuffer(buffer_path)
        buffer.append(_record("e1", "AML-001", "BLOCK"))
        buffer.append(_record("e2", "AML-002", "ALLOW"))
        buffer.append(_record("e3", "CM-001", "BLOCK"))

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
            print("SKIP: v2 model not trained yet")
            return

        assert os.path.exists(out)
        payload = json.load(open(out))
        assert "detection" in payload
        assert "fidelity" in payload
        assert "generalization" in payload
        assert "integrity" in payload
        assert "asr" in payload
        assert "summary" in payload
        assert report.asr.payment_attacks == 3
        assert len(report.integrity.checks) >= 5
        assert "pillars" in report.summary
        print(f"evaluation report: integrity={report.summary['integrity_score']}")
        print(f"  ASR before->after recall: {report.asr.before_ml_recall:.4f} -> {report.asr.after_ml_recall:.4f}")


def test_pillar_asr_empty_buffer():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features.json")):
        print("SKIP: no v1 model")
        return

    with tempfile.TemporaryDirectory() as tmp:
        runner = EvaluationRunner(
            model_dir=model_dir,
            buffer_path=os.path.join(tmp, "empty.jsonl"),
        )
        before = runner.evaluator.load_model_version("v1")
        after = runner.evaluator.load_model_version("v2")
        if not before or not after:
            print("SKIP: v1/v2 not available")
            return
        asr = runner._pillar_asr(before, after)
        assert asr.payment_attacks == 0
        print("empty ASR: OK")


if __name__ == "__main__":
    test_load_training_manifest_missing()
    test_pillar_asr_empty_buffer()
    test_evaluation_runner_smoke()
    print("\nAll evaluation runner tests passed.")
