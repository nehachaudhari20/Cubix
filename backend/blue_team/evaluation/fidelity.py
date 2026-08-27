"""
Phase 11b — Fidelity checks: amount, timing, and behavior score distributions.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from ..schemas import DistributionCheck, FidelityMetrics
from .context import EvaluationContext


def _bucket_stats(values: pd.Series, scores: np.ndarray, n_buckets: int = 5) -> List[Dict[str, Any]]:
    if len(values) == 0:
        return []
    try:
        buckets = pd.qcut(values, q=min(n_buckets, len(values)), duplicates="drop")
    except ValueError:
        return []
    out = []
    for label, idx in buckets.groupby(buckets, observed=False).groups.items():
        idx_list = list(idx)
        out.append({
            "bucket": str(label),
            "count": len(idx_list),
            "mean_score": round(float(np.mean(scores[idx_list])), 6),
        })
    return out


def run_fidelity_checks(
    ctx: EvaluationContext,
    *,
    n_baseline_legit: int = 500,
    n_baseline_fraud: int = 500,
) -> FidelityMetrics:
    """Score distribution fidelity vs amount, timing, and velocity behavior."""
    model = ctx.after
    df, proba = ctx.score_baseline(model, n_legit=n_baseline_legit, n_fraud=n_baseline_fraud)
    legit_mask = df["is_fraud"] == 0
    fraud_mask = df["is_fraud"] == 1
    legit_scores = proba[legit_mask.values]
    fraud_scores = proba[fraud_mask.values]

    amount_corr = 0.0
    amount_ks = 0.0
    amount_buckets: List[Dict[str, Any]] = []
    if legit_mask.any() and "amount" in df.columns:
        amounts = pd.to_numeric(df.loc[legit_mask, "amount"], errors="coerce").fillna(0)
        if len(amounts) > 2 and amounts.std() > 0:
            amount_corr = float(np.corrcoef(amounts, legit_scores)[0, 1])
        amount_buckets = _bucket_stats(amounts, legit_scores)
        if len(amounts) > 20:
            median_amt = amounts.median()
            low = legit_scores[amounts.values <= median_amt]
            high = legit_scores[amounts.values > median_amt]
            if len(low) > 5 and len(high) > 5:
                amount_ks = float(ks_2samp(low, high).statistic)

    hour_std = 0.0
    hour_profile: Dict[str, float] = {}
    timing_ks = 0.0
    if "hour_of_day" in df.columns and legit_mask.any():
        legit_df = df.loc[legit_mask].copy()
        legit_df["_score"] = legit_scores
        hour_means = legit_df.groupby("hour_of_day")["_score"].mean()
        hour_std = float(hour_means.std()) if len(hour_means) > 1 else 0.0
        hour_profile = {str(int(k)): round(float(v), 6) for k, v in hour_means.items()}
        if len(hour_means) > 3:
            night = legit_df[legit_df["hour_of_day"].between(0, 5)]["_score"]
            day = legit_df[legit_df["hour_of_day"].between(9, 17)]["_score"]
            if len(night) > 5 and len(day) > 5:
                timing_ks = float(ks_2samp(night, day).statistic)

    day_spread = 0.0
    if "day_of_week" in df.columns and legit_mask.any():
        legit_df = df.loc[legit_mask].copy()
        legit_df["_score"] = legit_scores
        dow_means = legit_df.groupby("day_of_week")["_score"].mean()
        day_spread = float(dow_means.max() - dow_means.min()) if len(dow_means) > 1 else 0.0

    rail_spread = 0.0
    if "payment_rail" in df.columns and legit_mask.any():
        legit_df = df.loc[legit_mask].copy()
        legit_df["_score"] = legit_scores
        rail_means = legit_df.groupby("payment_rail")["_score"].mean()
        rail_spread = float(rail_means.max() - rail_means.min()) if len(rail_means) > 1 else 0.0

    velocity_corr = 0.0
    for vel_col in ("transaction_count_last_24h", "velocity_score", "avg_amount_last_7d"):
        if vel_col in df.columns and legit_mask.sum() > 5:
            vel = pd.to_numeric(df.loc[legit_mask, vel_col], errors="coerce").fillna(0)
            if vel.std() > 0:
                velocity_corr = max(
                    velocity_corr,
                    abs(float(np.corrcoef(vel, legit_scores)[0, 1])),
                )
            break

    checks = [
        DistributionCheck(
            name="amount_correlation",
            passed=abs(amount_corr) <= 0.25,
            value=round(abs(amount_corr), 6),
            threshold=0.25,
            detail="Legit score vs amount should stay weakly correlated",
        ),
        DistributionCheck(
            name="amount_ks",
            passed=amount_ks <= 0.35,
            value=round(amount_ks, 6),
            threshold=0.35,
            detail="KS between low/high amount legit score distributions",
        ),
        DistributionCheck(
            name="timing_ks",
            passed=timing_ks <= 0.40,
            value=round(timing_ks, 6),
            threshold=0.40,
            detail="KS between night vs business-hour legit scores",
        ),
        DistributionCheck(
            name="velocity_correlation",
            passed=velocity_corr <= 0.30,
            value=round(velocity_corr, 6),
            threshold=0.30,
            detail="Legit score vs velocity/activity features",
        ),
    ]

    return FidelityMetrics(
        legit_mean_score=round(float(np.mean(legit_scores)), 6) if len(legit_scores) else 0.0,
        legit_std_score=round(float(np.std(legit_scores)), 6) if len(legit_scores) else 0.0,
        fraud_mean_score=round(float(np.mean(fraud_scores)), 6) if len(fraud_scores) else 0.0,
        score_separation=round(
            float(np.mean(fraud_scores) - np.mean(legit_scores))
            if len(fraud_scores) and len(legit_scores)
            else 0.0,
            6,
        ),
        amount_score_correlation=round(amount_corr, 6),
        amount_ks_stat=round(amount_ks, 6),
        amount_buckets=amount_buckets,
        hour_score_std=round(hour_std, 6),
        hour_profile=hour_profile,
        day_of_week_spread=round(day_spread, 6),
        timing_ks_stat=round(timing_ks, 6),
        rail_score_spread=round(rail_spread, 6),
        velocity_correlation=round(velocity_corr, 6),
        legit_samples=int(legit_mask.sum()),
        fraud_samples=int(fraud_mask.sum()),
        checks=checks,
        all_checks_passed=all(c.passed for c in checks),
    )
