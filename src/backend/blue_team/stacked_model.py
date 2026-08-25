"""
Stacked FraudShield v3 runtime model (Phase 10b).
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import xgboost as xgb

from .features import FeatureBuilder
from .schemas import FraudShieldPrediction


class StackedFraudShieldModel:
    """Runtime scorer for XGB + LGB + LR stacked ensemble."""

    def __init__(
        self,
        spec: Dict[str, Any],
        model_dir: str,
        xgb_model: Any,
        lgb_model: Any,
        log_model: Any,
        meta_model: Any,
        feature_builder: Optional[FeatureBuilder] = None,
    ):
        self.spec = spec
        self.model_dir = model_dir
        self.xgb_model = xgb_model
        self.lgb_model = lgb_model
        self.log_model = log_model
        self.meta_model = meta_model
        self.feature_builder = feature_builder or FeatureBuilder()
        self.feature_order = spec.get("feature_order", [])
        self.categorical_features = spec.get("categorical_features", [])
        self.categorical_mappings = spec.get("categorical_mappings", {})
        self.unseen_code = spec.get("unseen_category_code", -1)
        self.threshold = float(spec.get("decision_threshold", 0.5))
        self.model_type = "StackedEnsemble"
        self.version = spec.get("version", "v3")

    @classmethod
    def load(cls, model_dir: str, spec_path: Optional[str] = None) -> Optional["StackedFraudShieldModel"]:
        path = Path(model_dir)
        spec_file = Path(spec_path) if spec_path else path / "features_v3.json"
        if not spec_file.exists():
            spec_file = path / "features.json"
        if not spec_file.exists():
            return None

        with open(spec_file) as f:
            spec = json.load(f)
        if spec.get("model_type") != "StackedEnsemble":
            return None

        base = spec.get("base_models", {})
        meta_rel = spec.get("meta_model", "fraudshield_v3/meta.pkl")
        meta_path = path / meta_rel
        if not meta_path.exists():
            return None

        xgb_rel = base.get("xgboost", "fraudshield_v3/xgb.json")
        xgb_path = path / xgb_rel
        xgb_booster = xgb.XGBClassifier()
        xgb_booster.load_model(str(xgb_path))

        lgb_model = None
        lgb_rel = base.get("lightgbm")
        if lgb_rel:
            lgb_path = path / lgb_rel
            if lgb_path.exists():
                import lightgbm as lgb
                lgb_model = lgb.Booster(model_file=str(lgb_path))

        log_rel = base.get("logistic", "fraudshield_v3/logistic.pkl")
        log_path = path / log_rel
        with open(log_path, "rb") as f:
            log_model = pickle.load(f)

        with open(meta_path, "rb") as f:
            meta_model = pickle.load(f)

        return cls(
            spec=spec,
            model_dir=str(path),
            xgb_model=xgb_booster,
            lgb_model=lgb_model,
            log_model=log_model,
            meta_model=meta_model,
        )

    def _vector_from_row(self, row: Dict[str, Any]) -> List[float]:
        return self.feature_builder.to_model_vector(
            row,
            self.feature_order,
            self.categorical_features,
            self.categorical_mappings,
            self.unseen_code,
        )

    def _predict_proba_matrix(self, X: np.ndarray) -> np.ndarray:
        import pandas as pd
        X_df = pd.DataFrame(X, columns=self.feature_order)
        return self._predict_proba_frame(X_df)

    def _predict_proba_frame(self, X_df: pd.DataFrame) -> np.ndarray:
        p_xgb = self.xgb_model.predict_proba(X_df)[:, 1]
        if self.lgb_model is not None:
            p_lgb = np.asarray(self.lgb_model.predict(X_df.values), dtype=float)
        else:
            p_lgb = p_xgb
        p_log = self.log_model.predict_proba(X_df)[:, 1]
        stack = np.column_stack([p_xgb, p_lgb, p_log])
        return self.meta_model.predict_proba(stack)[:, 1]

    def predict_proba_from_encoded(self, X) -> np.ndarray:
        """Score already-encoded feature matrix (training/eval aligned path)."""
        import pandas as pd
        if isinstance(X, pd.DataFrame):
            X_df = X[self.feature_order]
        else:
            X_df = pd.DataFrame(X, columns=self.feature_order)
        return self._predict_proba_frame(X_df)

    def predict_proba_from_transaction(self, transaction: Dict[str, Any], state: Any) -> float:
        row = self.feature_builder.build(transaction, state)
        vector = self._vector_from_row(row)
        return float(self._predict_proba_matrix(np.array([vector]))[0])

    def predict_proba_from_features(self, features: Dict[str, Any]) -> float:
        row = dict(features)
        for col in self.feature_order:
            if col not in row:
                row[col] = 0
        vector = self._vector_from_row(row)
        return float(self._predict_proba_matrix(np.array([vector]))[0])

    def predict(self, transaction: Dict[str, Any], state: Any) -> FraudShieldPrediction:
        row = self.feature_builder.build(transaction, state)
        proba = self.predict_proba_from_transaction(transaction, state)
        missing = [f for f in self.feature_order if f not in row]
        return FraudShieldPrediction(
            fraud_probability=round(proba, 4),
            decision_threshold=self.threshold,
            is_fraud_predicted=proba >= self.threshold,
            model_version=self.version,
            features_used=list(self.feature_order),
            missing_features=missing,
        )

    # Adapter for FraudShieldModel-compatible interface
    @property
    def model(self):
        return self.meta_model
