"""
Stacked FraudShield v3 trainer (Phase 10b).

Level-0: XGBoost + LightGBM + LogisticRegression
Level-1: meta LogisticRegression on out-of-fold base predictions
"""

from __future__ import annotations

import json
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH
from .metrics import best_f1_threshold, evaluate_detection, threshold_at_fpr
from .training_mix import build_hardening_dataset
from .trainer import HardeningTrainer, DEFAULT_MODEL_DIR, BASELINE_DATA

try:
    import lightgbm as lgb
    HAVE_LGB = True
except ImportError:
    lgb = None
    HAVE_LGB = False


class StackedEnsembleTrainer:
    """Train FraudShield v3 stacked ensemble on baseline + buffer + hard negatives."""

    def __init__(
        self,
        model_dir: str = DEFAULT_MODEL_DIR,
        buffer_path: str = DEFAULT_BUFFER_PATH,
        baseline_path: str = BASELINE_DATA,
        n_folds: int = 5,
        random_state: int = 42,
    ):
        self.model_dir = Path(model_dir)
        self.buffer = EvidenceBuffer(buffer_path)
        self.base_trainer = HardeningTrainer(
            model_dir=model_dir,
            buffer_path=buffer_path,
            baseline_path=baseline_path,
        )
        self.n_folds = n_folds
        self.random_state = random_state

    def build_training_frame(
        self,
        n_baseline_legit: int = 4000,
        n_baseline_fraud: int = 4000,
        include_hard_negatives: bool = True,
        val_frac: float = 0.15,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """Build temporally split train/val frames with prioritized buffer mix."""
        spec_v1 = self.base_trainer.load_v1_spec()
        baseline_df = self.base_trainer.load_baseline_sample(n_baseline_legit, n_baseline_fraud)
        baseline_df = self.base_trainer.align_to_spec(baseline_df, spec_v1)

        records = self.buffer.read_all()
        train_df, val_df, manifest = build_hardening_dataset(
            baseline_df,
            records,
            include_hard_negatives=include_hard_negatives,
            val_frac=val_frac,
        )
        train_df = self.base_trainer.align_to_spec(train_df, spec_v1)
        val_df = self.base_trainer.align_to_spec(val_df, spec_v1)
        manifest["buffer_stats"] = self.buffer.stats()
        return train_df, val_df, manifest

    def _make_xgb(self, pos_weight: float) -> xgb.XGBClassifier:
        return xgb.XGBClassifier(
            n_estimators=400,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=8,
            reg_alpha=0.2,
            reg_lambda=3.0,
            gamma=0.1,
            scale_pos_weight=pos_weight,
            objective="binary:logistic",
            eval_metric="aucpr",
            tree_method="hist",
            random_state=self.random_state,
            n_jobs=-1,
            early_stopping_rounds=40,
        )

    def _make_lgb(self, pos_weight: float):
        if not HAVE_LGB:
            raise ImportError("LightGBM required for stacked v3 training")
        return lgb.LGBMClassifier(
            n_estimators=400,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_samples=40,
            reg_alpha=0.2,
            reg_lambda=2.0,
            scale_pos_weight=pos_weight,
            random_state=self.random_state,
            verbose=-1,
        )

    def _make_logistic(self) -> LogisticRegression:
        return LogisticRegression(
            max_iter=5000,
            class_weight="balanced",
            solver="lbfgs",
            C=0.5,
        )

    def _make_meta(self) -> LogisticRegression:
        """Meta-learner on base probabilities — L2 regularized, no class re-weighting."""
        return LogisticRegression(
            max_iter=5000,
            class_weight=None,
            solver="lbfgs",
            C=0.15,
        )

    def _base_proba(self, name: str, model: Any, X: pd.DataFrame) -> np.ndarray:
        if name == "xgboost":
            return model.predict_proba(X)[:, 1]
        if name == "lightgbm":
            return model.predict_proba(X)[:, 1]
        if name == "logistic":
            return model.predict_proba(X)[:, 1]
        raise ValueError(f"Unknown base model: {name}")

    def _oof_predictions(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        pos_weight: float,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Out-of-fold stacked features for meta-learner training."""
        skf = StratifiedKFold(n_splits=self.n_folds, shuffle=True, random_state=self.random_state)
        base_names = ["xgboost", "lightgbm", "logistic"]
        oof = np.zeros((len(y), len(base_names)))
        fold_models: Dict[str, List[Any]] = {n: [] for n in base_names}

        for fold_idx, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
            X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
            y_tr = y.iloc[tr_idx]

            xgb_model = self._make_xgb(pos_weight)
            xgb_model.fit(
                X_tr, y_tr,
                eval_set=[(X_va, y.iloc[va_idx])],
                verbose=False,
            )
            oof[va_idx, 0] = self._base_proba("xgboost", xgb_model, X_va)
            fold_models["xgboost"].append(xgb_model)

            if HAVE_LGB:
                lgb_model = self._make_lgb(pos_weight)
                lgb_model.fit(
                    X_tr, y_tr,
                    eval_set=[(X_va, y.iloc[va_idx])],
                    callbacks=[lgb.early_stopping(30, verbose=False)],
                )
                oof[va_idx, 1] = self._base_proba("lightgbm", lgb_model, X_va)
                fold_models["lightgbm"].append(lgb_model)
            else:
                oof[va_idx, 1] = oof[va_idx, 0]

            log_model = self._make_logistic()
            log_model.fit(X_tr, y_tr)
            oof[va_idx, 2] = self._base_proba("logistic", log_model, X_va)
            fold_models["logistic"].append(log_model)

        return oof, fold_models

    def train_v3(
        self,
        n_baseline_legit: int = 4000,
        n_baseline_fraud: int = 4000,
        val_frac: float = 0.15,
        include_hard_negatives: bool = True,
    ) -> Dict[str, Any]:
        """
        Train stacked v3 ensemble. Saves artifacts under model_dir.
        Does not swap active model (use swap_to_v3).
        """
        buffer_stats = self.buffer.stats()
        if buffer_stats["payment_records"] < 1:
            raise ValueError(
                "Adversarial buffer is empty. Run Red Team campaigns first."
            )

        spec_v1 = self.base_trainer.load_v1_spec()
        train_df, val_df, mix_stats = self.build_training_frame(
            n_baseline_legit,
            n_baseline_fraud,
            include_hard_negatives,
            val_frac=val_frac,
        )

        X_train, mappings = self.base_trainer.encode_features(train_df, spec_v1, fit=True)
        X_val, _ = self.base_trainer.encode_features(val_df, spec_v1, fit=False, mappings=mappings)
        y_train = train_df["is_fraud"].astype(int)
        y_val = val_df["is_fraud"].astype(int)

        pos_weight = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))

        oof, _ = self._oof_predictions(X_train, y_train, pos_weight)
        meta = self._make_meta()
        meta.fit(oof, y_train)

        xgb_final = self._make_xgb(pos_weight)
        xgb_final.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        lgb_final = None
        if HAVE_LGB:
            lgb_final = self._make_lgb(pos_weight)
            lgb_final.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50, verbose=False)],
            )

        log_final = self._make_logistic()
        log_final.fit(X_train, y_train)

        val_stack = self._stack_predict(
            X_val,
            xgb_final,
            lgb_final,
            log_final,
            meta,
        )

        # Tune threshold on baseline-only val rows (exclude adversarial buffer tail)
        val_baseline_mask = (
            val_df.get("source", pd.Series("baseline", index=val_df.index)) != "adversarial_buffer"
        ).values
        y_val_np = y_val.values
        if val_baseline_mask.sum() >= 50:
            thr_y = y_val_np[val_baseline_mask]
            thr_p = val_stack[val_baseline_mask]
        else:
            thr_y, thr_p = y_val_np, val_stack

        thr_f1 = best_f1_threshold(thr_y, thr_p)
        thr_1pct = threshold_at_fpr(thr_y, thr_p, target_fpr=0.01)
        thr_5pct = threshold_at_fpr(thr_y, thr_p, target_fpr=0.05)
        # Operational threshold: 5% FPR on baseline val (1% is reported separately)
        best_thr = thr_5pct

        detection = evaluate_detection("v3_stack", y_val_np, val_stack, threshold=best_thr)
        detection_f1 = evaluate_detection("v3_stack_f1", y_val_np, val_stack, threshold=thr_f1)
        detection_1pct = evaluate_detection("v3_stack_1pct", y_val_np, val_stack, threshold=thr_1pct)

        train_stack = self._stack_predict(X_train, xgb_final, lgb_final, log_final, meta)
        train_det = evaluate_detection("v3_stack_train", y_train.values, train_stack, threshold=best_thr)

        meta_weights = {
            "intercept": float(meta.intercept_[0]),
            "xgboost": float(meta.coef_[0][0]),
            "lightgbm": float(meta.coef_[0][1]),
            "logistic": float(meta.coef_[0][2]),
        }
        base_corr = np.corrcoef(oof.T).round(4).tolist()

        self.model_dir.mkdir(parents=True, exist_ok=True)
        v3_dir = self.model_dir / "fraudshield_v3"
        v3_dir.mkdir(parents=True, exist_ok=True)

        xgb_path = v3_dir / "xgb.json"
        xgb_final.save_model(str(xgb_path))

        lgb_path = v3_dir / "lgb.txt"
        if lgb_final is not None:
            lgb_final.booster_.save_model(str(lgb_path))

        log_path = v3_dir / "logistic.pkl"
        with open(log_path, "wb") as f:
            pickle.dump(log_final, f)

        meta_path = v3_dir / "meta.pkl"
        with open(meta_path, "wb") as f:
            pickle.dump(meta, f)

        from .anomaly import IsolationForestTrainer

        anomaly_trainer = IsolationForestTrainer(
            model_dir=str(self.model_dir),
            baseline_path=self.base_trainer.baseline_path,
        )
        anomaly_report = anomaly_trainer.train(n_legit=max(2000, n_baseline_legit))

        spec_v3 = {
            "model_type": "StackedEnsemble",
            "version": "v3",
            "parent_version": spec_v1.get("version", "v1"),
            "algorithm": "xgboost+lightgbm+logistic->meta_lr+isolation_forest",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "model_dir": "fraudshield_v3",
            "base_models": {
                "xgboost": "fraudshield_v3/xgb.json",
                "lightgbm": "fraudshield_v3/lgb.txt" if lgb_final else None,
                "logistic": "fraudshield_v3/logistic.pkl",
            },
            "meta_model": "fraudshield_v3/meta.pkl",
            "meta_features": ["xgboost", "lightgbm", "logistic"],
            "meta_weights": meta_weights,
            "meta_base_correlation": {
                "labels": ["xgboost", "lightgbm", "logistic"],
                "matrix": base_corr,
            },
            "anomaly_model": anomaly_report["relative_path"],
            "risk_blend": {"rule": 0.40, "ml": 0.45, "anomaly": 0.15},
            "anomaly_training": {
                "training_rows": anomaly_report["training_rows"],
                "score_p05": anomaly_report["score_p05"],
                "score_p95": anomaly_report["score_p95"],
            },
            "training_sources": mix_stats,
            "training_manifest": mix_stats,
            "split_method": mix_stats.get("split_method", "temporal_group"),
            "feature_order": spec_v1["feature_order"],
            "categorical_features": spec_v1.get("categorical_features", []),
            "categorical_mappings": mappings,
            "unseen_category_code": spec_v1.get("unseen_category_code", -1),
            "decision_threshold": best_thr,
            "threshold_f1": thr_f1,
            "threshold_at_1pct_fpr": thr_1pct,
            "threshold_at_5pct_fpr": thr_5pct,
            "threshold_tuned_on": "baseline_validation_at_5pct_fpr",
            "metrics": detection.model_dump(),
            "metrics_at_1pct_fpr": detection_1pct.model_dump(),
            "metrics_at_f1_threshold": detection_f1.model_dump(),
            "train_metrics": train_det.model_dump(),
            "overfit_gap_pr_auc": round(train_det.pr_auc - detection.pr_auc, 6),
            "n_folds": self.n_folds,
        }

        spec_path = self.model_dir / "features_v3.json"
        with open(spec_path, "w") as f:
            json.dump(spec_v3, f, indent=2)

        report = {
            "version": "v3",
            "mix_stats": mix_stats,
            "training_manifest": mix_stats,
            "detection": detection.model_dump(),
            "detection_at_f1": detection_f1.model_dump(),
            "train_detection": train_det.model_dump(),
            "meta_weights": meta_weights,
            "overfit_gap_pr_auc": round(train_det.pr_auc - detection.pr_auc, 6),
            "decision_threshold": best_thr,
            "threshold_at_1pct_fpr": thr_1pct,
            "threshold_at_5pct_fpr": thr_5pct,
            "spec_path": str(spec_path),
            "artifact_dir": str(v3_dir),
            "anomaly": anomaly_report,
        }
        report_path = self.model_dir / "hardening_report_v3.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        return report

    @staticmethod
    def _stack_predict(
        X: pd.DataFrame,
        xgb_model: Any,
        lgb_model: Any,
        log_model: Any,
        meta_model: Any,
    ) -> np.ndarray:
        p_xgb = xgb_model.predict_proba(X)[:, 1]
        p_lgb = lgb_model.predict_proba(X)[:, 1] if lgb_model is not None else p_xgb
        p_log = log_model.predict_proba(X)[:, 1]
        stack_X = np.column_stack([p_xgb, p_lgb, p_log])
        return meta_model.predict_proba(stack_X)[:, 1]

    def swap_to_v3(self) -> Dict[str, str]:
        """Promote v3 spec to active features.json."""
        import shutil

        v3_spec = self.model_dir / "features_v3.json"
        active_spec = self.model_dir / "features.json"
        backup = self.model_dir / "features_pre_v3_backup.json"

        if not v3_spec.exists():
            raise FileNotFoundError("features_v3.json not found — run train_v3() first")

        if active_spec.exists():
            shutil.copy(active_spec, backup)

        shutil.copy(v3_spec, active_spec)
        return {
            "active_spec": str(active_spec),
            "backup": str(backup) if backup.exists() else "",
            "model_type": "StackedEnsemble",
        }
