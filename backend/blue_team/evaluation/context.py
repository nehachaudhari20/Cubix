"""Shared evaluation context and scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from ..evaluator import HardeningEvaluator
from ..metrics import threshold_at_fpr
from ..schemas import TRAINABLE_ACTION_TYPES, EvidenceRecord
from ..trainer import FEATURE_DEFAULTS, HardeningTrainer
from .manifest import load_training_manifest

# FPR both models are pinned to when comparing at a matched operating point
DEFAULT_MATCHED_FPR = 0.05


@dataclass
class EvaluationContext:
    evaluator: HardeningEvaluator
    trainer: HardeningTrainer
    model_dir: Path
    before: Any
    after: Any
    before_version: str
    after_version: str
    manifest: Dict[str, Any]

    @classmethod
    def build(
        cls,
        evaluator: HardeningEvaluator,
        model_dir: Path,
        before_version: str,
        after_version: str,
    ) -> "EvaluationContext":
        before = evaluator.load_model_version(before_version)
        after = evaluator.load_model_version(after_version)
        if not before or not after:
            raise FileNotFoundError(
                f"Models required: before={before_version} after={after_version}"
            )
        manifest = load_training_manifest(model_dir, after_version)
        return cls(
            evaluator=evaluator,
            trainer=evaluator.trainer,
            model_dir=model_dir,
            before=before,
            after=after,
            before_version=before_version,
            after_version=after_version,
            manifest=manifest,
        )

    def payment_records(self) -> List[EvidenceRecord]:
        return [
            r
            for r in self.evaluator.buffer.read_all()
            if r.action_type == "initiate_payment" and r.label == 1
        ]

    def attack_records(self) -> List[EvidenceRecord]:
        """Adversarial rows from every adjudicated surface, not just payment."""
        return [
            r
            for r in self.evaluator.buffer.read_all()
            if r.action_type in TRAINABLE_ACTION_TYPES and r.label == 1
        ]

    def matched_thresholds(
        self,
        target_fpr: float = DEFAULT_MATCHED_FPR,
        n_legit: int = 2000,
        n_fraud: int = 2000,
    ) -> Tuple[float, float, float]:
        """
        Thresholds putting `before` and `after` at the same baseline FPR.

        Comparing two models at their own calibrated thresholds conflates a
        change in ranking quality with a change in operating point: v3 can rank
        strictly better yet appear to "lose recall" purely because its threshold
        was set more conservatively. Returns (before_thr, after_thr, actual_fpr).
        """
        df, before_proba = self.score_baseline(self.before, n_legit, n_fraud)
        y = df["is_fraud"].astype(int).values
        _, after_proba = self.score_baseline(self.after, n_legit, n_fraud)

        before_thr = threshold_at_fpr(y, before_proba, target_fpr)
        after_thr = threshold_at_fpr(y, after_proba, target_fpr)
        return float(before_thr), float(after_thr), float(target_fpr)

    def record_to_row(self, record: EvidenceRecord, model: Any) -> Dict[str, Any]:
        row = dict(record.features)
        for col in model.feature_order:
            if col not in row:
                row[col] = FEATURE_DEFAULTS.get(col, 0)
        return row

    def score_records(self, records: List[EvidenceRecord], model: Any) -> List[float]:
        return [
            self.evaluator._predict_row_proba(model, self.record_to_row(r, model))
            for r in records
        ]

    def score_baseline(
        self, model: Any, n_legit: int, n_fraud: int
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        df = self.trainer.load_baseline_sample(n_legit=n_legit, n_fraud=n_fraud)
        X = self.evaluator._encode_for_model(df, model)
        proba = self.evaluator._predict_proba(model, X)
        return df, proba

    def detection_delta_dict(
        self, before: Dict[str, Any], after: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "pr_auc_delta": round(after.get("pr_auc", 0) - before.get("pr_auc", 0), 6),
            "recall_delta": round(after.get("recall", 0) - before.get("recall", 0), 6),
            "fpr_delta": round(after.get("fpr", 0) - before.get("fpr", 0), 6),
            "recall_at_1pct_fpr_delta": round(
                after.get("recall_at_1pct_fpr", 0) - before.get("recall_at_1pct_fpr", 0),
                6,
            ),
        }
