"""
Hardening Evaluator — compare FraudShield v1 vs v2 on buffer and baseline holdout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH
from .fraudshield import FraudShieldModel, DEFAULT_MODEL_DIR
from .schemas import HardeningReport
from .trainer import HardeningTrainer, FEATURE_DEFAULTS


class HardeningEvaluator:
    """Evaluate model improvement after Loop B hardening."""

    def __init__(
        self,
        model_dir: str = DEFAULT_MODEL_DIR,
        buffer_path: str = DEFAULT_BUFFER_PATH,
    ):
        self.model_dir = Path(model_dir)
        self.buffer = EvidenceBuffer(buffer_path)
        self.trainer = HardeningTrainer(model_dir=model_dir, buffer_path=buffer_path)

    def load_model_version(self, version: str) -> Optional[FraudShieldModel]:
        """Load v1 (active) or v2 (features_v2.json)."""
        if version == "v2":
            spec_path = self.model_dir / "features_v2.json"
            if not spec_path.exists():
                return None
            import lightgbm as lgb
            with open(spec_path) as f:
                spec = json.load(f)
            model_path = self.model_dir / spec["model_file"]
            if not model_path.exists():
                return None
            booster = lgb.Booster(model_file=str(model_path))
            return FraudShieldModel(model=booster, spec=spec, model_dir=str(self.model_dir))
        return FraudShieldModel.load(str(self.model_dir))

    def _score_buffer_records(self, model: FraudShieldModel) -> List[float]:
        """Score all buffer payment records using stored features."""
        scores = []
        for record in self.buffer.read_all():
            if record.action_type != "initiate_payment":
                continue
            row = dict(record.features)
            for col in model.feature_order:
                if col not in row:
                    row[col] = FEATURE_DEFAULTS.get(col, 0)
            vector = model.feature_builder.to_model_vector(
                row,
                model.feature_order,
                model.categorical_features,
                model.categorical_mappings,
                model.unseen_code,
            )
            if model.model_type == "LightGBM":
                scores.append(float(model.model.predict([vector])[0]))
            else:
                import xgboost as xgb
                dmat = xgb.DMatrix([vector], feature_names=model.feature_order)
                scores.append(float(model.model.predict(dmat)[0]))
        return scores

    def evaluate_buffer(self, v1: FraudShieldModel, v2: FraudShieldModel) -> Dict[str, Any]:
        """Compare mean fraud score on adversarial buffer (all label=1)."""
        s1 = self._score_buffer_records(v1)
        s2 = self._score_buffer_records(v2)
        if not s1:
            return {"records": 0, "v1_mean": 0, "v2_mean": 0, "lift": 0}

        bypassed = [
            r for r in self.buffer.read_all()
            if r.action_type == "initiate_payment" and r.evasion_outcome == "bypassed"
        ]

        return {
            "records": len(s1),
            "v1_mean_score": round(float(np.mean(s1)), 4),
            "v2_mean_score": round(float(np.mean(s2)), 4),
            "lift": round(float(np.mean(s2) - np.mean(s1)), 4),
            "v1_recall_at_threshold": round(float(np.mean(np.array(s1) >= v1.threshold)), 4),
            "v2_recall_at_threshold": round(float(np.mean(np.array(s2) >= v2.threshold)), 4),
            "bypassed_count": len(bypassed),
        }

    def evaluate_baseline_holdout(self, model: FraudShieldModel, n: int = 500) -> Dict[str, float]:
        """Score a small baseline fraud holdout sample."""
        try:
            df = self.trainer.load_baseline_sample(n_legit=0, n_fraud=n)
        except Exception:
            return {"fraud_recall": 0.0, "samples": 0}

        spec = {"feature_order": model.feature_order, "categorical_features": model.categorical_features}
        aligned = self.trainer.align_to_spec(df, spec)
        X, _ = self.trainer.encode_features(aligned, {
            "feature_order": model.feature_order,
            "categorical_features": model.categorical_features,
            "categorical_mappings": model.categorical_mappings,
            "unseen_category_code": model.unseen_code,
        }, fit=False)

        if model.model_type == "LightGBM":
            proba = model.model.predict(X.values)
        else:
            import xgboost as xgb
            dmat = xgb.DMatrix(X, feature_names=model.feature_order)
            proba = model.model.predict(dmat)

        y = aligned["is_fraud"].astype(int).values
        recall = float((proba >= model.threshold)[y == 1].mean()) if (y == 1).any() else 0.0
        return {
            "fraud_recall": round(recall, 4),
            "mean_fraud_score": round(float(np.mean(proba)), 4),
            "samples": len(y),
        }

    def full_report(self) -> HardeningReport:
        """Generate before/after hardening comparison report."""
        v1 = self.load_model_version("v1")
        v2 = self.load_model_version("v2")

        if not v1 or not v2:
            raise FileNotFoundError("Both v1 and v2 models required for comparison")

        buffer_eval = self.evaluate_buffer(v1, v2)
        v1_holdout = self.evaluate_baseline_holdout(v1)
        v2_holdout = self.evaluate_baseline_holdout(v2)

        improved = (
            buffer_eval["v2_mean_score"] >= buffer_eval["v1_mean_score"]
            and v2_holdout["fraud_recall"] >= v1_holdout["fraud_recall"] * 0.95
        )

        return HardeningReport(
            v1_version=v1.version,
            v2_version=v2.version,
            buffer_records=buffer_eval["records"],
            v1_buffer_mean_score=buffer_eval["v1_mean_score"],
            v2_buffer_mean_score=buffer_eval["v2_mean_score"],
            buffer_score_lift=buffer_eval["lift"],
            v1_baseline_fraud_recall=v1_holdout["fraud_recall"],
            v2_baseline_fraud_recall=v2_holdout["fraud_recall"],
            bypassed_attacks=buffer_eval["bypassed_count"],
            recommend_swap=improved,
            details={
                "buffer": buffer_eval,
                "v1_holdout": v1_holdout,
                "v2_holdout": v2_holdout,
            },
        )
