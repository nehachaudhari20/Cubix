"""
FraudShieldModel — loads trained XGBoost/LightGBM and scores sandbox transactions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .features import FeatureBuilder
from .schemas import FraudShieldPrediction

DEFAULT_MODEL_DIR = os.environ.get(
    "FRAUDSHIELD_MODEL_DIR",
    os.path.join("data", "models"),
)


class FraudShieldModel:
    """Runtime FraudShield v1 classifier."""

    def __init__(
        self,
        model: Any,
        spec: Dict[str, Any],
        model_dir: str,
        feature_builder: Optional[FeatureBuilder] = None,
    ):
        self.model = model
        self.spec = spec
        self.model_dir = model_dir
        self.feature_builder = feature_builder or FeatureBuilder()
        self.feature_order = spec.get("feature_order", [])
        self.categorical_features = spec.get("categorical_features", [])
        self.categorical_mappings = spec.get("categorical_mappings", {})
        self.unseen_code = spec.get("unseen_category_code", -1)
        self.threshold = float(spec.get("decision_threshold", 0.5))
        self.model_type = spec.get("model_type", "unknown")
        self.version = spec.get("version", "v1")

    @classmethod
    def load(cls, model_dir: str = DEFAULT_MODEL_DIR) -> Optional["FraudShieldModel"]:
        """Load model + features.json from directory. Returns None if not found."""
        path = Path(model_dir)
        spec_path = path / "features.json"
        if not spec_path.exists():
            return None

        with open(spec_path, "r") as f:
            spec = json.load(f)

        model_file = spec.get("model_file", "fraudshield_v1.json")
        model_path = path / model_file
        if not model_path.exists():
            # Fallback to common names
            for candidate in ("fraudshield_v1.json", "fraud_detection_model.json", "fraud_detection_model.txt"):
                alt = path / candidate
                if alt.exists():
                    model_path = alt
                    model_file = candidate
                    break
            else:
                return None

        model_type = spec.get("model_type", "XGBoost")
        if model_type == "LightGBM" or str(model_path).endswith(".txt"):
            import lightgbm as lgb
            model = lgb.Booster(model_file=str(model_path))
        elif model_type == "XGBoost" or str(model_path).endswith(".json"):
            import xgboost as xgb
            booster = xgb.Booster()
            booster.load_model(str(model_path))
            model = booster
        else:
            return None

        spec["model_file"] = model_file
        return cls(model=model, spec=spec, model_dir=str(path))

    def predict_proba_from_transaction(
        self,
        transaction: Dict[str, Any],
        state: Any,
    ) -> float:
        """Return fraud probability for a sandbox transaction."""
        row = self.feature_builder.build(transaction, state)
        vector = self.feature_builder.to_model_vector(
            row,
            self.feature_order,
            self.categorical_features,
            self.categorical_mappings,
            self.unseen_code,
        )
        import numpy as np

        if self.model_type == "LightGBM":
            proba = float(self.model.predict([vector])[0])
        else:
            import xgboost as xgb
            dmat = xgb.DMatrix([vector], feature_names=self.feature_order)
            proba = float(self.model.predict(dmat)[0])
        return proba

    def predict(self, transaction: Dict[str, Any], state: Any) -> FraudShieldPrediction:
        """Full prediction with metadata."""
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

    # Legacy interface for RiskEngine (sklearn-style)
    def predict_proba(self, X):
        """Not used — prefer predict_proba_from_transaction."""
        raise NotImplementedError("Use predict_proba_from_transaction(transaction, state)")


def load_fraudshield(model_dir: str = DEFAULT_MODEL_DIR) -> Optional[FraudShieldModel]:
    """Convenience loader."""
    return FraudShieldModel.load(model_dir)
