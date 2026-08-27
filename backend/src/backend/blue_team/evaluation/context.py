"""Shared evaluation context and scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from ..evaluator import HardeningEvaluator
from ..schemas import EvidenceRecord
from ..trainer import FEATURE_DEFAULTS, HardeningTrainer
from .manifest import load_training_manifest


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
