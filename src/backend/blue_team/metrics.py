"""
Shared fraud-detection evaluation metrics (Phase 10a).

Used by train_model.py, HardeningEvaluator, and future EvaluationRunner.
Primary metric: PR-AUC. Deployment-oriented: recall at fixed FPR, queue precision.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

from .schemas import DetectionMetrics

ArrayLike = Union[np.ndarray, Sequence[float], Sequence[int]]

# Analysts review the top-scored fraction of volume
REVIEW_CAPACITY = 0.01

# Real-world fraud prevalences for precision reporting (dataset is often 50/50)
REPORT_PREVALENCES = (0.005, 0.015)

# Partial AUC / recall targets (false-positive rate caps)
DEFAULT_FPR_TARGETS = (0.01, 0.001)


def _as_numpy(y: ArrayLike) -> np.ndarray:
    return np.asarray(y, dtype=int)


def _as_float_proba(proba: ArrayLike) -> np.ndarray:
    return np.asarray(proba, dtype=float)


def recall_at_fpr(y: ArrayLike, proba: ArrayLike, target_fpr: float) -> float:
    """Recall (TPR) when FPR is capped at target_fpr."""
    y_arr = _as_numpy(y)
    p_arr = _as_float_proba(proba)
    fpr, tpr, _ = roc_curve(y_arr, p_arr)
    return float(np.interp(target_fpr, fpr, tpr))


def fpr_at_threshold(y: ArrayLike, proba: ArrayLike, threshold: float) -> float:
    """False positive rate at a fixed decision threshold."""
    y_arr = _as_numpy(y)
    pred = _as_float_proba(proba) >= threshold
    legit = y_arr == 0
    if not legit.any():
        return 0.0
    return float(pred[legit].mean())


def precision_at_prevalence(
    y: ArrayLike,
    proba: ArrayLike,
    threshold: float,
    prevalence: float,
) -> tuple[float, float, float]:
    """Precision at a deployment prevalence (prevalence-invariant from TPR/FPR)."""
    y_arr = _as_numpy(y)
    pred = _as_float_proba(proba) >= threshold
    tpr = float(pred[y_arr == 1].mean()) if (y_arr == 1).any() else 0.0
    fpr = float(pred[y_arr == 0].mean()) if (y_arr == 0).any() else 0.0
    num = prevalence * tpr
    den = num + (1.0 - prevalence) * fpr
    precision = float(num / den) if den > 0 else 0.0
    return precision, tpr, fpr


def queue_precision(
    y: ArrayLike,
    proba: ArrayLike,
    capacity: float = REVIEW_CAPACITY,
) -> tuple[float, int]:
    """Precision among the highest-scoring `capacity` share of rows."""
    y_arr = _as_numpy(y)
    p_arr = _as_float_proba(proba)
    k = max(1, int(len(p_arr) * capacity))
    idx = np.argsort(p_arr)[::-1][:k]
    return float(y_arr[idx].mean()), k


def best_f1_threshold(y: ArrayLike, proba: ArrayLike) -> float:
    """Threshold maximizing F1 on the given labels/scores."""
    y_arr = _as_numpy(y)
    p_arr = _as_float_proba(proba)
    prec, rec, thr = precision_recall_curve(y_arr, p_arr)
    f1 = 2 * prec * rec / np.clip(prec + rec, 1e-12, None)
    if len(thr) == 0:
        return 0.5
    return float(thr[max(0, int(np.nanargmax(f1)) - 1)])


def evaluate_detection(
    name: str,
    y: ArrayLike,
    proba: ArrayLike,
    threshold: Optional[float] = None,
    *,
    review_capacity: float = REVIEW_CAPACITY,
    fpr_targets: Sequence[float] = DEFAULT_FPR_TARGETS,
) -> DetectionMetrics:
    """
    Full detection metric bundle for one model on one labeled set.

    Returns structured metrics aligned with the Evaluation framework (Detection pillar).
    """
    y_arr = _as_numpy(y)
    p_arr = _as_float_proba(proba)

    if threshold is None:
        threshold = best_f1_threshold(y_arr, p_arr)

    pred = (p_arr >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_arr, pred, labels=[0, 1]).ravel()
    q_prec, k = queue_precision(y_arr, p_arr, review_capacity)

    recall_fpr_map: Dict[str, float] = {}
    for target in fpr_targets:
        key = f"recall_at_{target * 100:g}pct_fpr".replace(".", "p")
        recall_fpr_map[key] = recall_at_fpr(y_arr, p_arr, target)

    return DetectionMetrics(
        model=name,
        samples=int(len(y_arr)),
        fraud_rate=round(float(y_arr.mean()), 6),
        pr_auc=round(float(average_precision_score(y_arr, p_arr)), 6),
        roc_auc=round(float(roc_auc_score(y_arr, p_arr)), 6),
        f1=round(float(f1_score(y_arr, pred, zero_division=0)), 6),
        precision=round(float(precision_score(y_arr, pred, zero_division=0)), 6),
        recall=round(float(recall_score(y_arr, pred, zero_division=0)), 6),
        fpr=round(fpr_at_threshold(y_arr, p_arr, threshold), 6),
        recall_at_1pct_fpr=round(recall_fpr_map.get("recall_at_1pct_fpr", 0.0), 6),
        recall_at_0p1pct_fpr=round(recall_fpr_map.get("recall_at_0p1pct_fpr", 0.0), 6),
        queue_precision_top1pct=round(q_prec, 6),
        brier=round(float(brier_score_loss(y_arr, p_arr)), 6),
        threshold=round(float(threshold), 6),
        tn=int(tn),
        fp=int(fp),
        fn=int(fn),
        tp=int(tp),
        review_queue_size=int(k),
    )


def evaluate_detection_dict(
    name: str,
    y: ArrayLike,
    proba: ArrayLike,
    threshold: Optional[float] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Backward-compatible dict output (train_model.py tables)."""
    metrics = evaluate_detection(name, y, proba, threshold, **kwargs)
    return metrics.model_dump()


def precision_at_prevalence_report(
    y: ArrayLike,
    proba: ArrayLike,
    threshold: float,
    prevalences: Sequence[float] = REPORT_PREVALENCES,
) -> Dict[str, float]:
    """Map prevalence -> expected precision at deployment."""
    return {
        str(pi): round(precision_at_prevalence(y, proba, threshold, pi)[0], 6)
        for pi in prevalences
    }


def hard_negative_fpr(
    y: ArrayLike,
    proba: ArrayLike,
    threshold: float,
    hard_negative_mask: ArrayLike,
) -> Dict[str, float]:
    """FPR on hard negatives vs ordinary legit (integrity / fidelity checks)."""
    y_arr = _as_numpy(y)
    mask = np.asarray(hard_negative_mask, dtype=bool)
    pred = _as_float_proba(proba) >= threshold

    hn = mask & (y_arr == 0)
    cn = (~mask) & (y_arr == 0)
    return {
        "hard_negative_fpr": round(float(pred[hn].mean()), 6) if hn.any() else 0.0,
        "hard_negative_count": int(hn.sum()),
        "ordinary_legit_fpr": round(float(pred[cn].mean()), 6) if cn.any() else 0.0,
        "ordinary_legit_count": int(cn.sum()),
    }


def compare_detection(
    before: DetectionMetrics,
    after: DetectionMetrics,
) -> Dict[str, Any]:
    """Before/after deltas for Loop B and EvaluationRunner."""
    return {
        "before_model": before.model,
        "after_model": after.model,
        "pr_auc_delta": round(after.pr_auc - before.pr_auc, 6),
        "recall_delta": round(after.recall - before.recall, 6),
        "fpr_delta": round(after.fpr - before.fpr, 6),
        "recall_at_1pct_fpr_delta": round(
            after.recall_at_1pct_fpr - before.recall_at_1pct_fpr, 6
        ),
        "buffer_recall_improved": after.recall >= before.recall,
    }


def detection_summary_table(metrics: Sequence[DetectionMetrics]) -> List[Dict[str, Any]]:
    """Rows for printing or JSON export."""
    show = (
        "model", "pr_auc", "roc_auc", "recall_at_1pct_fpr", "recall_at_0p1pct_fpr",
        "queue_precision_top1pct", "f1", "precision", "recall", "fpr", "brier",
    )
    rows = []
    for m in metrics:
        row = m.model_dump()
        rows.append({k: row[k] for k in show if k in row})
    return rows
