"""
Hardening Evaluator — compare FraudShield v1 vs v2 on buffer and baseline holdout.

Phase 10a: uses shared DetectionMetrics from blue_team.metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH
from .fraudshield import FraudShieldModel, DEFAULT_MODEL_DIR
from .metrics import (
    compare_detection,
    evaluate_detection,
    hard_negative_fpr,
)
from .schemas import DetectionMetrics, HardeningReport
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

    def _predict_proba(self, model: FraudShieldModel, X: pd.DataFrame) -> np.ndarray:
        if model.model_type == "LightGBM":
            return np.asarray(model.model.predict(X.values), dtype=float)
        import xgboost as xgb
        dmat = xgb.DMatrix(X, feature_names=model.feature_order)
        return np.asarray(model.model.predict(dmat), dtype=float)

    def _encode_for_model(self, df: pd.DataFrame, model: FraudShieldModel) -> pd.DataFrame:
        spec = {
            "feature_order": model.feature_order,
            "categorical_features": model.categorical_features,
            "categorical_mappings": model.categorical_mappings,
            "unseen_category_code": model.unseen_code,
        }
        aligned = self.trainer.align_to_spec(df, spec)
        X, _ = self.trainer.encode_features(aligned, spec, fit=False)
        return X

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
        """Compare scores on adversarial buffer (all fraud attempts, label=1)."""
        s1 = self._score_buffer_records(v1)
        s2 = self._score_buffer_records(v2)
        if not s1:
            return {"records": 0, "v1_mean_score": 0, "v2_mean_score": 0, "lift": 0}

        bypassed = [
            r for r in self.buffer.read_all()
            if r.action_type == "initiate_payment" and r.evasion_outcome == "bypassed"
        ]

        y_all = np.ones(len(s1), dtype=int)
        v1_det = evaluate_detection("v1_buffer", y_all, s1, threshold=v1.threshold)
        v2_det = evaluate_detection("v2_buffer", y_all, s2, threshold=v2.threshold)

        return {
            "records": len(s1),
            "v1_mean_score": round(float(np.mean(s1)), 4),
            "v2_mean_score": round(float(np.mean(s2)), 4),
            "lift": round(float(np.mean(s2) - np.mean(s1)), 4),
            "v1_recall_at_threshold": round(v1_det.recall, 4),
            "v2_recall_at_threshold": round(v2_det.recall, 4),
            "v1_detection": v1_det.model_dump(),
            "v2_detection": v2_det.model_dump(),
            "detection_delta": compare_detection(v1_det, v2_det),
            "bypassed_count": len(bypassed),
        }

    def evaluate_baseline_holdout(
        self,
        model: FraudShieldModel,
        n_fraud: int = 500,
        n_legit: int = 500,
    ) -> Dict[str, Any]:
        """Score balanced baseline holdout with full detection metrics."""
        try:
            df = self.trainer.load_baseline_sample(n_legit=n_legit, n_fraud=n_fraud)
        except Exception:
            return {"samples": 0, "fraud_recall": 0.0, "detection": {}}

        X = self._encode_for_model(df, model)
        proba = self._predict_proba(model, X)
        y = df["is_fraud"].astype(int).values

        detection = evaluate_detection(
            f"{model.version}_holdout",
            y,
            proba,
            threshold=model.threshold,
        )

        hn_mask = df.get("meta_hard_negative", pd.Series(False, index=df.index)).fillna(False)
        if hn_mask.any() or (y == 0).any():
            hn_stats = hard_negative_fpr(y, proba, model.threshold, hn_mask.values)
        else:
            hn_stats = {}

        return {
            "fraud_recall": detection.recall,
            "mean_fraud_score": round(float(np.mean(proba)), 4),
            "samples": detection.samples,
            "detection": detection.model_dump(),
            "hard_negative_stats": hn_stats,
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

        v1_det = v1_holdout.get("detection") or {}
        v2_det = v2_holdout.get("detection") or {}

        improved = (
            buffer_eval["v2_mean_score"] >= buffer_eval["v1_mean_score"]
            and v2_holdout["fraud_recall"] >= v1_holdout["fraud_recall"] * 0.95
            and v2_det.get("fpr", 1.0) <= v1_det.get("fpr", 1.0) * 1.05
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
                "v1_detection": v1_det,
                "v2_detection": v2_det,
            },
        )
