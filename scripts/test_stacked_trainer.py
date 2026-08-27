#!/usr/bin/env python3
"""Phase 10b: stacked FraudShield v3 training smoke test."""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.blue_team.schemas import EvidenceRecord
from backend.blue_team.stacked_model import StackedFraudShieldModel
from backend.blue_team.stacked_trainer import StackedEnsembleTrainer
from backend.blue_team.anomaly import load_anomaly_scorer


def _load_feature_order() -> list:
    spec_path = Path(os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")) / "features.json"
    if not spec_path.exists():
        return ["amount", "payment_rail", "device_age_days", "is_new_device", "hour_of_day"]
    with open(spec_path) as f:
        return json.load(f).get("feature_order", [])


def _synthetic_features(amount: float = 12000.0) -> dict:
    order = _load_feature_order()
    base = {
        "amount": amount,
        "payment_rail": "upi",
        "device_age_days": 2,
        "is_new_device": 1,
        "hour_of_day": 14,
        "merchant_risk_score": 0.35,
        "velocity_score": 0.4,
        "account_age_days": 30,
        "is_new_beneficiary": 1,
    }
    return {col: base.get(col, 0) for col in order}


def _seed_buffer(path: str, n: int = 5) -> None:
    buf = EvidenceBuffer(path)
    for i in range(n):
        buf.append(EvidenceRecord(
            evidence_id=f"ev_{uuid.uuid4().hex[:8]}",
            campaign_id=f"camp_{i}",
            attack_family="AUT-001",
            action_type="initiate_payment",
            sandbox_decision="BLOCK",
            evasion_outcome="blocked",
            label=1,
            features=_synthetic_features(15000 + i * 500),
            amount=15000 + i * 500,
            step=1,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))


def main() -> int:
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    v1_spec = Path(model_dir) / "features.json"
    if not v1_spec.exists():
        print("SKIP: data/models/features.json missing (run train_model.py first)")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        buffer_path = os.path.join(tmp, "evidence.jsonl")
        _seed_buffer(buffer_path, n=8)

        out_dir = os.path.join(tmp, "models")
        os.makedirs(out_dir, exist_ok=True)

        # Copy v1 spec so stacked trainer can extend feature mappings
        import shutil
        shutil.copy(v1_spec, os.path.join(out_dir, "features.json"))

        trainer = StackedEnsembleTrainer(
            model_dir=out_dir,
            buffer_path=buffer_path,
            baseline_path=os.environ.get("FRAUDSHIELD_BASELINE_DATA", "master_dataset.json"),
            n_folds=3,
        )
        report = trainer.train_v3(
            n_baseline_legit=400,
            n_baseline_fraud=400,
            val_frac=0.15,
            include_hard_negatives=False,
        )
        assert report["version"] == "v3"
        assert Path(report["spec_path"]).exists()
        print(f"v3 trained: pr_auc={report['detection']['pr_auc']:.4f}")

        loaded = StackedFraudShieldModel.load(out_dir)
        assert loaded is not None
        score = loaded.predict_proba_from_features(_synthetic_features())
        assert 0.0 <= score <= 1.0
        print(f"runtime score: {score:.4f}")

        scorer = load_anomaly_scorer(out_dir)
        if scorer:
            anom = scorer.score_features(_synthetic_features(50000))
            print(f"anomaly score: {anom:.4f}")
        assert Path(out_dir, "fraudshield_v3", "isolation_forest.pkl").exists()

    print("OK: test_stacked_trainer passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
