"""
Phase 11e — Attack Success Rate (ASR) before vs after hardening.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np

from ..metrics import evaluate_detection
from ..schemas import ASRMetrics, FamilyASR
from .context import EvaluationContext


def run_asr_evaluation(ctx: EvaluationContext) -> ASRMetrics:
    """Compute ASR before/after from adversarial buffer."""
    records = ctx.payment_records()
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

    hist_bypass_rate = bypassed / total
    ml_asr_before = 1.0 - before_det.recall
    ml_asr_after = 1.0 - after_det.recall

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
    )


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
        "per_family": [f.model_dump() for f in asr.per_family],
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
