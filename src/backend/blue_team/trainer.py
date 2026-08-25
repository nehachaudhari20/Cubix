"""
Hardening Trainer — Loop B: merge baseline + adversarial buffer → FraudShield v2.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH

DEFAULT_MODEL_DIR = os.environ.get("FRAUDSHIELD_MODEL_DIR", os.path.join("data", "models"))
BASELINE_DATA = os.environ.get("FRAUDSHIELD_BASELINE_DATA", "master_dataset.json")

# Defaults for features present in v1 spec but missing from sandbox buffer rows
FEATURE_DEFAULTS = {
    "location_country": "IN",
    "location_region": "unknown",
    "transaction_type": "transfer",
    "currency": "INR",
    "campaign_step": 1,
    "merchant_familiarity_score": 0.5,
    "card_present": 0,
    "auth_success": 1,
    "merchant_category_code": "5411",
}


class HardeningTrainer:
    """Retrain FraudShield on baseline + Red Team adversarial evidence."""

    def __init__(
        self,
        model_dir: str = DEFAULT_MODEL_DIR,
        buffer_path: str = DEFAULT_BUFFER_PATH,
        baseline_path: str = BASELINE_DATA,
    ):
        self.model_dir = Path(model_dir)
        self.buffer = EvidenceBuffer(buffer_path)
        self.baseline_path = baseline_path

    def load_v1_spec(self) -> Dict[str, Any]:
        spec_path = self.model_dir / "features.json"
        if not spec_path.exists():
            raise FileNotFoundError(f"v1 spec not found: {spec_path}")
        with open(spec_path, "r") as f:
            return json.load(f)

    def load_baseline_sample(
        self,
        n_legit: int = 4000,
        n_fraud: int = 4000,
    ) -> pd.DataFrame:
        """Sample balanced baseline rows from master_dataset.json."""
        with open(self.baseline_path, "r") as f:
            payload = json.load(f)
        df = pd.DataFrame(payload["transactions"])

        legit = df[df["is_fraud"] == 0].sample(n=min(n_legit, (df["is_fraud"] == 0).sum()), random_state=42)
        fraud = df[df["is_fraud"] == 1].sample(n=min(n_fraud, (df["is_fraud"] == 1).sum()), random_state=42)
        sample = pd.concat([legit, fraud], ignore_index=True)
        sample["source"] = "baseline"
        return sample

    def buffer_to_dataframe(self) -> pd.DataFrame:
        """Convert adversarial buffer export to dataframe aligned with training schema."""
        rows = self.buffer.export_training_rows()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["source"] = "adversarial_buffer"
        return df

    def align_to_spec(self, df: pd.DataFrame, spec: Dict[str, Any]) -> pd.DataFrame:
        """Ensure all feature_order columns exist with sensible defaults."""
        feature_order = spec["feature_order"]
        aligned = df.copy()
        for col in feature_order:
            if col not in aligned.columns:
                aligned[col] = FEATURE_DEFAULTS.get(col, 0)
        if "is_fraud" not in aligned.columns:
            aligned["is_fraud"] = 1
        return aligned

    def encode_features(
        self,
        df: pd.DataFrame,
        spec: Dict[str, Any],
        fit: bool = True,
        mappings: Optional[Dict] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Dict[str, int]]]:
        """Encode categoricals using v1 mappings extended with new buffer values."""
        feature_order = spec["feature_order"]
        cats = spec.get("categorical_features", [])
        mappings = mappings or dict(spec.get("categorical_mappings", {}))
        unseen = spec.get("unseen_category_code", -1)

        X = pd.DataFrame(index=df.index)
        for col in feature_order:
            if col in cats:
                vals = df[col].astype(str).fillna("NA")
                if fit:
                    existing = mappings.get(col, {})
                    next_id = max(existing.values(), default=-1) + 1
                    mapping = dict(existing)
                    for v in sorted(vals.unique()):
                        if v not in mapping:
                            mapping[v] = next_id
                            next_id += 1
                    mappings[col] = mapping
                else:
                    mapping = mappings.get(col, {})
                X[col] = vals.map(mapping).fillna(unseen).astype(int)
            else:
                X[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(float)
        return X, mappings

    def train_v2(
        self,
        n_baseline_legit: int = 4000,
        n_baseline_fraud: int = 4000,
        val_frac: float = 0.15,
    ) -> Dict[str, Any]:
        """
        Train FraudShield v2 on baseline sample + adversarial buffer.
        Saves fraudshield_v2.* and features_v2.json (does not swap active model).
        """
        buffer_stats = self.buffer.stats()
        if buffer_stats["payment_records"] < 1:
            raise ValueError(
                "Adversarial buffer is empty. Run Red Team campaigns first "
                "(python src/scripts/test_evidence_buffer.py)."
            )

        spec_v1 = self.load_v1_spec()
        baseline_df = self.load_baseline_sample(n_baseline_legit, n_baseline_fraud)
        buffer_df = self.buffer_to_dataframe()

        baseline_aligned = self.align_to_spec(baseline_df, spec_v1)
        buffer_aligned = self.align_to_spec(buffer_df, spec_v1)

        combined = pd.concat([baseline_aligned, buffer_aligned], ignore_index=True)
        combined = combined.sample(frac=1, random_state=42).reset_index(drop=True)

        n_val = max(1, int(len(combined) * val_frac))
        val_df = combined.iloc[:n_val]
        train_df = combined.iloc[n_val:]

        X_train, mappings = self.encode_features(train_df, spec_v1, fit=True)
        X_val, _ = self.encode_features(val_df, spec_v1, fit=False, mappings=mappings)
        y_train = train_df["is_fraud"].astype(int)
        y_val = val_df["is_fraud"].astype(int)

        import lightgbm as lgb
        from sklearn.metrics import average_precision_score, roc_auc_score

        pos_weight = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))
        model = lgb.LGBMClassifier(
            n_estimators=400,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=pos_weight,
            random_state=42,
            verbose=-1,
        )
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )

        val_proba = model.predict_proba(X_val)[:, 1]
        pr_auc = float(average_precision_score(y_val, val_proba))
        roc_auc = float(roc_auc_score(y_val, val_proba))

        # Threshold tuned on validation F1
        from sklearn.metrics import precision_recall_curve
        prec, rec, thr = precision_recall_curve(y_val, val_proba)
        f1 = 2 * prec * rec / np.clip(prec + rec, 1e-12, None)
        best_thr = float(thr[max(0, int(np.nanargmax(f1)) - 1)])

        self.model_dir.mkdir(parents=True, exist_ok=True)
        model_path = self.model_dir / "fraudshield_v2.txt"
        model.booster_.save_model(str(model_path))

        spec_v2 = {
            "model_file": "fraudshield_v2.txt",
            "model_type": "LightGBM",
            "version": "v2",
            "parent_version": spec_v1.get("version", "v1"),
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "training_sources": {
                "baseline_rows": len(baseline_aligned),
                "buffer_rows": len(buffer_aligned),
                "buffer_families": buffer_stats["families"],
            },
            "feature_order": spec_v1["feature_order"],
            "categorical_features": spec_v1.get("categorical_features", []),
            "categorical_mappings": mappings,
            "unseen_category_code": spec_v1.get("unseen_category_code", -1),
            "decision_threshold": best_thr,
            "threshold_tuned_on": "hardening validation split",
            "metrics": {"pr_auc": pr_auc, "roc_auc": roc_auc},
        }

        spec_v2_path = self.model_dir / "features_v2.json"
        with open(spec_v2_path, "w") as f:
            json.dump(spec_v2, f, indent=2)

        report_path = self.model_dir / "hardening_report.json"
        report = {
            "version": "v2",
            "baseline_sample": len(baseline_aligned),
            "buffer_rows": len(buffer_aligned),
            "buffer_stats": buffer_stats,
            "val_pr_auc": pr_auc,
            "val_roc_auc": roc_auc,
            "decision_threshold": best_thr,
            "model_path": str(model_path),
            "spec_path": str(spec_v2_path),
        }
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        return report

    def swap_to_v2(self) -> Dict[str, str]:
        """Promote v2 to active model (updates features.json). Backs up v1 spec."""
        v2_spec = self.model_dir / "features_v2.json"
        active_spec = self.model_dir / "features.json"
        v1_backup = self.model_dir / "features_v1_backup.json"

        if not v2_spec.exists():
            raise FileNotFoundError("features_v2.json not found — run train_v2() first")

        if active_spec.exists():
            shutil.copy(active_spec, v1_backup)

        shutil.copy(v2_spec, active_spec)
        return {
            "active_spec": str(active_spec),
            "v1_backup": str(v1_backup) if v1_backup.exists() else "",
            "model_file": "fraudshield_v2.txt",
        }

    def train_v3(
        self,
        n_baseline_legit: int = 4000,
        n_baseline_fraud: int = 4000,
        val_frac: float = 0.15,
        include_hard_negatives: bool = True,
    ) -> Dict[str, Any]:
        """Train stacked FraudShield v3 (delegates to StackedEnsembleTrainer)."""
        from .stacked_trainer import StackedEnsembleTrainer

        trainer = StackedEnsembleTrainer(
            model_dir=str(self.model_dir),
            buffer_path=str(self.buffer.path),
            baseline_path=self.baseline_path,
        )
        return trainer.train_v3(
            n_baseline_legit=n_baseline_legit,
            n_baseline_fraud=n_baseline_fraud,
            val_frac=val_frac,
            include_hard_negatives=include_hard_negatives,
        )

    def swap_to_v3(self) -> Dict[str, str]:
        from .stacked_trainer import StackedEnsembleTrainer

        return StackedEnsembleTrainer(
            model_dir=str(self.model_dir),
            buffer_path=str(self.buffer.path),
            baseline_path=self.baseline_path,
        ).swap_to_v3()
