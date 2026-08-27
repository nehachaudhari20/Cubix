"""
Phase 11e — Attack Success Rate (ASR) before vs after hardening.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np

from ..metrics import evaluate_detection
from ..schemas import ASRMetrics, FamilyASR, SurfaceASR
from .context import EvaluationContext


def run_asr_evaluation(ctx: EvaluationContext) -> ASRMetrics:
    """Compute ASR before/after from adversarial buffer, across all surfaces."""
    records = ctx.attack_records()
    if not records:
        return ASRMetrics()

    before, after = ctx.before, ctx.after
    bypassed = sum(
        1 for r in records
        if r.evasion_outcome == "bypassed" or r.sandbox_decision == "ALLOW"
    )
    blocked = sum(
        1 for r in records
        if r.evasion_outcome in ("blocked", "challenged")
        or r.sandbox_decision in ("BLOCK", "CHALLENGE")
    )
    total = len(records)

    s_before = ctx.score_records(records, before)
    s_after = ctx.score_records(records, after)
    y = np.ones(len(s_before), dtype=int)

    before_det = evaluate_detection("asr_before", y, s_before, threshold=before.threshold)
    after_det = evaluate_detection("asr_after", y, s_after, threshold=after.threshold)

    per_family = _per_family_asr(records, s_before, s_after, before.threshold, after.threshold)
    per_surface = _per_surface_asr(records, s_before, s_after, before.threshold, after.threshold)

    hist_bypass_rate = bypassed / total
    ml_asr_before = 1.0 - before_det.recall
    ml_asr_after = 1.0 - after_det.recall

    matched = _matched_point_asr(ctx, s_before, s_after, y)

    return ASRMetrics(
        payment_attacks=total,
        historical_bypass_count=bypassed,
        historical_bypass_rate=round(hist_bypass_rate, 6),
        historical_block_rate=round(blocked / total, 6),
        before_ml_recall=round(before_det.recall, 6),
        after_ml_recall=round(after_det.recall, 6),
        ml_recall_lift=round(after_det.recall - before_det.recall, 6),
        before_ml_asr=round(ml_asr_before, 6),
        after_ml_asr=round(ml_asr_after, 6),
        projected_bypass_rate_after=round(ml_asr_after, 6),
        asr_reduction=round(ml_asr_before - ml_asr_after, 6),
        per_family=per_family,
        per_surface=per_surface,
        **matched,
    )


def _matched_point_asr(
    ctx: EvaluationContext,
    s_before: List[float],
    s_after: List[float],
    y: np.ndarray,
) -> Dict[str, Any]:
    """ASR with both models pinned to the same baseline FPR."""
    try:
        thr_before, thr_after, fpr = ctx.matched_thresholds()
    except Exception:
        return {}

    before_det = evaluate_detection("asr_before_matched", y, s_before, threshold=thr_before)
    after_det = evaluate_detection("asr_after_matched", y, s_after, threshold=thr_after)
    asr_before = 1.0 - before_det.recall
    asr_after = 1.0 - after_det.recall

    return {
        "matched_fpr": round(fpr, 6),
        "before_threshold_matched": round(thr_before, 6),
        "after_threshold_matched": round(thr_after, 6),
        "before_ml_recall_matched": round(before_det.recall, 6),
        "after_ml_recall_matched": round(after_det.recall, 6),
        "ml_recall_lift_matched": round(after_det.recall - before_det.recall, 6),
        "before_ml_asr_matched": round(asr_before, 6),
        "after_ml_asr_matched": round(asr_after, 6),
        "asr_reduction_matched": round(asr_before - asr_after, 6),
    }


def _per_surface_asr(
    records,
    s_before: List[float],
    s_after: List[float],
    thr_before: float,
    thr_after: float,
) -> List[SurfaceASR]:
    by_surface: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(records):
        by_surface[r.surface].append(i)

    rows: List[SurfaceASR] = []
    for surface, indices in sorted(by_surface.items()):
        idx = np.asarray(indices, dtype=int)
        sub = [records[i] for i in idx]
        bypassed = sum(
            1 for r in sub
            if r.evasion_outcome == "bypassed" or r.sandbox_decision == "ALLOW"
        )
        b_recall = float(np.mean(np.asarray(s_before)[idx] >= thr_before))
        a_recall = float(np.mean(np.asarray(s_after)[idx] >= thr_after))
        rows.append(
            SurfaceASR(
                surface=surface,
                attacks=len(sub),
                historical_bypass_rate=round(bypassed / len(sub), 6),
                before_ml_recall=round(b_recall, 6),
                after_ml_recall=round(a_recall, 6),
                asr_reduction=round(a_recall - b_recall, 6),
            )
        )
    return rows


def _per_family_asr(
    records,
    s_before: List[float],
    s_after: List[float],
    thr_before: float,
    thr_after: float,
) -> List[FamilyASR]:
    by_family: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(records):
        by_family[r.attack_family].append(i)

    rows: List[FamilyASR] = []
    for family, indices in sorted(by_family.items()):
        idx = np.asarray(indices, dtype=int)
        sub = [records[i] for i in idx]
        bypassed = sum(
            1 for r in sub
            if r.evasion_outcome == "bypassed" or r.sandbox_decision == "ALLOW"
        )
        b_scores = np.asarray(s_before)[idx]
        a_scores = np.asarray(s_after)[idx]
        b_recall = float(np.mean(b_scores >= thr_before))
        a_recall = float(np.mean(a_scores >= thr_after))
        rows.append(
            FamilyASR(
                family=family,
                attacks=len(sub),
                historical_bypass_rate=round(bypassed / len(sub), 6),
                before_ml_recall=round(b_recall, 6),
                after_ml_recall=round(a_recall, 6),
                asr_reduction=round((1 - b_recall) - (1 - a_recall), 6),
            )
        )
    return rows


def asr_summary_dict(asr: ASRMetrics) -> Dict[str, Any]:
    """Compact ASR block for loop_runner / API."""
    return {
        "payment_attacks": asr.payment_attacks,
        "historical_bypass_rate": asr.historical_bypass_rate,
        "before_ml_asr": asr.before_ml_asr,
        "after_ml_asr": asr.after_ml_asr,
        "asr_reduction": asr.asr_reduction,
        "before_ml_recall": asr.before_ml_recall,
        "after_ml_recall": asr.after_ml_recall,
        "ml_recall_lift": asr.ml_recall_lift,
        "matched_fpr": asr.matched_fpr,
        "before_ml_asr_matched": asr.before_ml_asr_matched,
        "after_ml_asr_matched": asr.after_ml_asr_matched,
        "asr_reduction_matched": asr.asr_reduction_matched,
        "per_family": [f.model_dump() for f in asr.per_family],
        "per_surface": [s.model_dump() for s in asr.per_surface],
    }


def run_asr_for_loop(
    *,
    model_dir: str,
    buffer_path: str,
    before_version: str = "v1",
    after_version: str = "v2",
) -> Dict[str, Any]:
    """Lightweight ASR entry point for loop_runner."""
    from pathlib import Path

    from ..evaluator import HardeningEvaluator

    evaluator = HardeningEvaluator(model_dir=model_dir, buffer_path=buffer_path)
    ctx = EvaluationContext.build(
        evaluator, Path(model_dir), before_version, after_version
    )
    asr = run_asr_evaluation(ctx)
    return asr_summary_dict(asr)
