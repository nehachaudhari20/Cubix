"""
Isolation Forest anomaly scorer (Phase 10c).

Trained on legitimate baseline traffic only. Higher score = more anomalous.
"""

from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .features import FeatureBuilder
from .trainer import HardeningTrainer, DEFAULT_MODEL_DIR, BASELINE_DATA

DEFAULT_ANOMALY_PATH = "fraudshield_v3/isolation_forest.pkl"


class AnomalyScorer:
    """Runtime isolation-forest anomaly scorer (0-1, higher = more anomalous)."""

    def __init__(
        self,
        model: IsolationForest,
        spec: Dict[str, Any],
        feature_builder: Optional[FeatureBuilder] = None,
    ):
        self.model = model
        self.spec = spec
        self.feature_builder = feature_builder or FeatureBuilder()
        self.feature_order = spec.get("feature_order", [])
        self.categorical_features = spec.get("categorical_features", [])
        self.categorical_mappings = spec.get("categorical_mappings", {})
        self.unseen_code = spec.get("unseen_category_code", -1)
        self.score_p05 = float(spec.get("score_p05", 0.0))
        self.score_p95 = float(spec.get("score_p95", 1.0))
        self.version = spec.get("version", "v3-anomaly")

    def _encode_row(self, row: Dict[str, Any]) -> np.ndarray:
        vector = self.feature_builder.to_model_vector(
            row,
            self.feature_order,
            self.categorical_features,
            self.categorical_mappings,
            self.unseen_code,
        )
        return np.array([vector], dtype=float)

    def _normalize(self, raw: float) -> float:
        span = max(self.score_p95 - self.score_p05, 1e-9)
        scaled = (raw - self.score_p05) / span
        return float(np.clip(scaled, 0.0, 1.0))

    def score_features(self, features: Dict[str, Any]) -> float:
        row = dict(features)
        for col in self.feature_order:
            if col not in row:
                row[col] = 0
        X = self._encode_row(row)
        raw = float(-self.model.decision_function(X)[0])
        return round(self._normalize(raw), 4)

    def score_transaction(self, transaction: Dict[str, Any], state: Any) -> float:
        row = self.feature_builder.build(transaction, state)
        return self.score_features(row)


class IsolationForestTrainer:
    """Train isolation forest on legitimate baseline rows."""

    def __init__(
        self,
        model_dir: str = DEFAULT_MODEL_DIR,
        baseline_path: str = BASELINE_DATA,
        contamination: float = 0.05,
        random_state: int = 42,
    ):
        self.model_dir = Path(model_dir)
        self.base_trainer = HardeningTrainer(
            model_dir=model_dir,
            baseline_path=baseline_path,
        )
        self.contamination = contamination
        self.random_state = random_state

    def train(
        self,
        n_legit: int = 8000,
        *,
        artifact_subdir: str = "fraudshield_v3",
    ) -> Dict[str, Any]:
        spec_v1 = self.base_trainer.load_v1_spec()
        baseline = self.base_trainer.load_baseline_sample(n_legit=n_legit, n_fraud=0)
        aligned = self.base_trainer.align_to_spec(baseline, spec_v1)
        X, mappings = self.base_trainer.encode_features(aligned, spec_v1, fit=True)

        model = IsolationForest(
            n_estimators=200,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1,
        )
        model.fit(X.values)

        raw_train = -model.decision_function(X.values)
        score_p05 = float(np.percentile(raw_train, 5))
        score_p95 = float(np.percentile(raw_train, 95))

        out_dir = self.model_dir / artifact_subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = out_dir / "isolation_forest.pkl"

        payload = {
            "model": model,
            "spec": {
                "version": "v3-anomaly",
                "algorithm": "IsolationForest",
                "feature_order": spec_v1["feature_order"],
                "categorical_features": spec_v1.get("categorical_features", []),
                "categorical_mappings": mappings,
                "unseen_category_code": spec_v1.get("unseen_category_code", -1),
                "score_p05": score_p05,
                "score_p95": score_p95,
                "contamination": self.contamination,
                "training_rows": len(aligned),
            },
        }
        with open(artifact_path, "wb") as f:
            pickle.dump(payload, f)

        return {
            "artifact_path": str(artifact_path),
            "training_rows": len(aligned),
            "score_p05": score_p05,
            "score_p95": score_p95,
            "relative_path": f"{artifact_subdir}/isolation_forest.pkl",
        }


def load_anomaly_scorer(model_dir: str = DEFAULT_MODEL_DIR) -> Optional[AnomalyScorer]:
    """Load anomaly model from active spec or v3 spec."""
    path = Path(model_dir)

    for spec_name in ("features.json", "features_v3.json"):
        spec_path = path / spec_name
        if not spec_path.exists():
            continue
        with open(spec_path) as f:
            spec = json.load(f)
        rel = spec.get("anomaly_model") or (
            DEFAULT_ANOMALY_PATH if spec.get("version") == "v3" else None
        )
        if not rel:
            continue
        artifact = path / rel
        if artifact.exists():
            with open(artifact, "rb") as f:
                payload = pickle.load(f)
            return AnomalyScorer(model=payload["model"], spec=payload["spec"])

    fallback = path / DEFAULT_ANOMALY_PATH
    if fallback.exists():
        with open(fallback, "rb") as f:
            payload = pickle.load(f)
        return AnomalyScorer(model=payload["model"], spec=payload["spec"])

    return None


def risk_blend_weights(spec: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Resolve rule / ML / anomaly blend weights."""
    defaults = {"rule": 0.40, "ml": 0.45, "anomaly": 0.15}
    if spec and spec.get("risk_blend"):
        blend = spec["risk_blend"]
        return {
            "rule": float(blend.get("rule", defaults["rule"])),
            "ml": float(blend.get("ml", defaults["ml"])),
            "anomaly": float(blend.get("anomaly", defaults["anomaly"])),
        }
    return {
        "rule": float(os.environ.get("FRAUDSHIELD_BLEND_RULE", defaults["rule"])),
        "ml": float(os.environ.get("FRAUDSHIELD_BLEND_ML", defaults["ml"])),
        "anomaly": float(os.environ.get("FRAUDSHIELD_BLEND_ANOMALY", defaults["anomaly"])),
    }


def combine_risk_scores(
    rule_risk: float,
    ml_score: float,
    anomaly_score: float,
    *,
    spec: Optional[Dict[str, Any]] = None,
) -> float:
    weights = risk_blend_weights(spec)
    total_w = weights["rule"] + weights["ml"] + weights["anomaly"]
    if total_w <= 0:
        total_w = 1.0
    combined = (
        rule_risk * weights["rule"]
        + ml_score * weights["ml"]
        + anomaly_score * weights["anomaly"]
    ) / total_w
    return round(min(0.95, combined), 3)
