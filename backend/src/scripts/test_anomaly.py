#!/usr/bin/env python3
"""Phase 10c: Isolation Forest anomaly scorer tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.blue_team.anomaly import (
    AnomalyScorer,
    IsolationForestTrainer,
    combine_risk_scores,
    load_anomaly_scorer,
)
from backend.sandbox import PaymentSandbox


def test_train_and_score():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    v1_spec = os.path.join(model_dir, "features.json")
    if not os.path.exists(v1_spec):
        print("SKIP: features.json missing")
        return

    import tempfile
    import shutil
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "models")
        os.makedirs(out, exist_ok=True)
        shutil.copy(v1_spec, os.path.join(out, "features.json"))

        trainer = IsolationForestTrainer(model_dir=out)
        report = trainer.train(n_legit=1000)
        assert Path(report["artifact_path"]).exists()
        print(f"trained IF on {report['training_rows']} legit rows")

        scorer = load_anomaly_scorer(out)
        assert scorer is not None

        normal = scorer.score_features({"amount": 5000, "payment_rail": "upi", "hour_of_day": 14})
        weird = scorer.score_features({"amount": 999999, "payment_rail": "wire", "hour_of_day": 3})
        assert 0.0 <= normal <= 1.0
        assert weird >= normal
        print(f"anomaly normal={normal:.4f} weird={weird:.4f}")


def test_combine_risk_scores():
    combined = combine_risk_scores(0.6, 0.7, 0.8)
    assert 0.0 < combined <= 0.95
    print(f"combined risk: {combined}")


def test_sandbox_blend():
    sandbox = PaymentSandbox()
    sandbox.add_customer("C_anom", "Test", "PAN1", "1990-01-01", "City", trust_score=0.7)
    sandbox.add_device("D_anom", "C_anom")

    result = sandbox.process_transaction({
        "transaction_id": "T_anom",
        "customer_id": "C_anom",
        "device_id": "D_anom",
        "amount": 45000,
        "payment_rail": "upi",
        "authentication_method": "otp",
        "merchant_risk_score": 0.5,
    })
    state = result.get("state", {})
    assert "risk_score" in state
    print(
        f"sandbox: risk={state.get('risk_score')} ml={state.get('ml_score')} "
        f"anomaly={state.get('anomaly_score', 'n/a')}"
    )


def main() -> int:
    test_train_and_score()
    test_combine_risk_scores()
    test_sandbox_blend()
    print("OK: test_anomaly passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
