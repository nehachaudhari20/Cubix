"""
Phase 11a — Detection suite on holdout, temporal test, and adversarial buffer.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..metrics import detection_summary_table, evaluate_detection
from ..schemas import DetectionMetrics, DetectionSuiteResult
from ..training_mix import temporal_train_val_split
from .context import EvaluationContext


def _metrics_dict(model: Any, y, proba, name: str) -> Dict[str, Any]:
    det = evaluate_detection(name, y, proba, threshold=model.threshold)
    return det.model_dump()


def run_detection_suite(
    ctx: EvaluationContext,
    *,
    n_baseline_legit: int = 500,
    n_baseline_fraud: int = 500,
    test_val_frac: float = 0.15,
) -> DetectionSuiteResult:
    """Full detection suite: holdout, temporal test split, adversarial buffer."""
    before, after = ctx.before, ctx.after

    # --- Holdout (balanced baseline sample) ---
    before_holdout = ctx.evaluator.evaluate_baseline_holdout(
        before, n_fraud=n_baseline_fraud, n_legit=n_baseline_legit
    )
    after_holdout = ctx.evaluator.evaluate_baseline_holdout(
        after, n_fraud=n_baseline_fraud, n_legit=n_baseline_legit
    )
    before_h = before_holdout.get("detection") or {}
    after_h = after_holdout.get("detection") or {}

    # --- Temporal test split (baseline only, no buffer leakage) ---
    baseline_df = ctx.trainer.load_baseline_sample(
        n_legit=n_baseline_legit, n_fraud=n_baseline_fraud
    )
    baseline_df["source"] = "baseline"
    _, test_df, split_meta = temporal_train_val_split(baseline_df, val_frac=test_val_frac)

    test_before = _score_split(ctx, before, test_df, f"{before.version}_test")
    test_after = _score_split(ctx, after, test_df, f"{after.version}_test")

    # --- Adversarial buffer (all fraud, label=1) ---
    buffer_eval = ctx.evaluator.evaluate_buffer(before, after)
    records = ctx.payment_records()
    buffer_before = _score_buffer_slice(ctx, before, records, f"{before.version}_buffer")
    buffer_after = _score_buffer_slice(ctx, after, records, f"{after.version}_buffer")

    suite_table: List[Dict[str, Any]] = []
    for label, b_det, a_det in (
        ("holdout", before_h, after_h),
        ("test", test_before, test_after),
        ("buffer", buffer_before, buffer_after),
    ):
        if b_det and a_det:
            suite_table.append({"slice": label, "phase": "before", **{k: b_det.get(k) for k in (
                "model", "samples", "pr_auc", "recall", "fpr", "recall_at_1pct_fpr", "f1"
            )}})
            suite_table.append({"slice": label, "phase": "after", **{k: a_det.get(k) for k in (
                "model", "samples", "pr_auc", "recall", "fpr", "recall_at_1pct_fpr", "f1"
            )}})

    holdout_delta = ctx.detection_delta_dict(before_h, after_h)
    test_delta = ctx.detection_delta_dict(test_before, test_after)
    buffer_delta = ctx.detection_delta_dict(buffer_before, buffer_after)

    before_metrics = [
        DetectionMetrics.model_validate(before_h),
        DetectionMetrics.model_validate(test_before),
        DetectionMetrics.model_validate(buffer_before),
    ]
    after_metrics = [
        DetectionMetrics.model_validate(after_h),
        DetectionMetrics.model_validate(test_after),
        DetectionMetrics.model_validate(buffer_after),
    ]

    return DetectionSuiteResult(
        holdout={
            "before": before_h,
            "after": after_h,
            "delta": holdout_delta,
            "hard_negative_stats": after_holdout.get("hard_negative_stats", {}),
        },
        test={
            "before": test_before,
            "after": test_after,
            "delta": test_delta,
            "split_meta": split_meta,
            "rows": len(test_df),
        },
        buffer={
            "comparison": buffer_eval,
            "before": buffer_before,
            "after": buffer_after,
            "delta": buffer_delta,
        },
        suite_table=suite_table,
        summary_table={
            "before": detection_summary_table(before_metrics),
            "after": detection_summary_table(after_metrics),
        },
        primary_metric="pr_auc",
        before_holdout_pr_auc=before_h.get("pr_auc", 0.0),
        after_holdout_pr_auc=after_h.get("pr_auc", 0.0),
        buffer_recall_lift=round(
            buffer_eval.get("v2_recall_at_threshold", 0.0)
            - buffer_eval.get("v1_recall_at_threshold", 0.0),
            6,
        ),
    )


def _score_split(ctx: EvaluationContext, model, df, name: str) -> Dict[str, Any]:
    if df.empty:
        return {}
    aligned = ctx.trainer.align_to_spec(df, ctx.trainer.load_v1_spec())
    X = ctx.evaluator._encode_for_model(aligned, model)
    proba = ctx.evaluator._predict_proba(model, X)
    y = aligned["is_fraud"].astype(int).values
    return _metrics_dict(model, y, proba, name)


def _score_buffer_slice(
    ctx: EvaluationContext, model, records, name: str
) -> Dict[str, Any]:
    if not records:
        return {}
    scores = ctx.score_records(records, model)
    y = np.ones(len(scores), dtype=int)
    return _metrics_dict(model, y, scores, name)
