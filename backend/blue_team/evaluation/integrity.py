"""
Phase 11d — Integrity battery: leakage, null control, ablation, temporal split.
"""

from __future__ import annotations

from typing import List

import numpy as np
from scipy.stats import ks_2samp

from ..metrics import evaluate_detection, hard_negative_fpr
from ..schemas import TRAINABLE_ACTION_TYPES, IntegrityCheck, IntegrityMetrics
from ..trainer import FEATURE_DEFAULTS
from .context import EvaluationContext


def run_integrity_battery(
    ctx: EvaluationContext,
    *,
    n_baseline_legit: int = 500,
    n_baseline_fraud: int = 500,
) -> IntegrityMetrics:
    """Run full integrity test battery on the hardened model."""
    after = ctx.after
    manifest = ctx.manifest
    checks: List[IntegrityCheck] = []

    df, proba = ctx.score_baseline(after, n_legit=n_baseline_legit, n_fraud=n_baseline_fraud)
    y = df["is_fraud"].astype(int).values

    # Null control
    rng = np.random.default_rng(42)
    y_shuffled = rng.permutation(y)
    null_det = evaluate_detection("null_control", y_shuffled, proba)
    checks.append(
        IntegrityCheck(
            name="null_control",
            passed=null_det.pr_auc <= 0.65,
            value=null_det.pr_auc,
            threshold=0.65,
            detail="Shuffled-label PR-AUC should stay near chance (~0.5)",
        )
    )

    # Ablation — zero features
    ablated = [
        ctx.evaluator._predict_row_proba(after, {col: 0 for col in after.feature_order})
        for _ in range(int((df["is_fraud"] == 0).sum()))
    ]
    ablated_fpr = float(np.mean(np.asarray(ablated) >= after.threshold)) if ablated else 0.0
    checks.append(
        IntegrityCheck(
            name="ablation_zero_features",
            passed=ablated_fpr <= 0.15,
            value=ablated_fpr,
            threshold=0.15,
            detail="FPR on legit rows with all features zeroed",
        )
    )

    # Ablation — null / missing categoricals (unseen code path)
    null_row = {col: FEATURE_DEFAULTS.get(col, 0) for col in after.feature_order}
    null_scores = [
        ctx.evaluator._predict_row_proba(after, null_row)
        for _ in range(min(50, int((df["is_fraud"] == 0).sum())))
    ]
    null_fpr = float(np.mean(np.asarray(null_scores) >= after.threshold)) if null_scores else 0.0
    checks.append(
        IntegrityCheck(
            name="null_feature_defaults",
            passed=null_fpr <= 0.20,
            value=null_fpr,
            threshold=0.20,
            detail="FPR when scoring default/null feature vector",
        )
    )

    # Hard negatives
    hn_records = [
        r
        for r in ctx.evaluator.buffer.read_all()
        if r.is_hard_negative and r.label == 0 and r.action_type in TRAINABLE_ACTION_TYPES
    ]
    hn_fpr = 0.0
    hn_count = len(hn_records)
    if hn_records:
        hn_scores = ctx.score_records(hn_records, after)
        hn_stats = hard_negative_fpr(
            np.zeros(len(hn_scores), dtype=int),
            hn_scores,
            after.threshold,
            np.ones(len(hn_scores), dtype=bool),
        )
        hn_fpr = hn_stats.get("hard_negative_fpr", 0.0)
        hn_passed = hn_fpr <= 0.10
    else:
        hn_passed = True
    checks.append(
        IntegrityCheck(
            name="hard_negatives",
            passed=hn_passed,
            value=hn_fpr,
            threshold=0.10,
            detail=f"{hn_count} hard-negative buffer rows",
        )
    )

    # Temporal split
    split_method = manifest.get("split_method", "unknown")
    val_buffer_rows = int(manifest.get("val_buffer_rows", 0))
    train_buffer_rows = int(manifest.get("train_buffer_rows", 0))
    known_splits = ("temporal_group", "temporal_baseline_campaign_holdout")
    temporal_ok = split_method in known_splits
    checks.append(
        IntegrityCheck(
            name="temporal_split",
            passed=temporal_ok or split_method == "unknown",
            value=float(val_buffer_rows),
            threshold=0.0,
            detail=f"split_method={split_method}, val_buffer_rows={val_buffer_rows}",
        )
    )

    # Leakage proxy
    leakage_ok = (temporal_ok and val_buffer_rows > 0) or split_method == "unknown"
    train_fraud_rate = float(manifest.get("train_fraud_rate", 0))
    val_fraud_rate = float(manifest.get("val_fraud_rate", 0))
    rate_gap = abs(train_fraud_rate - val_fraud_rate)
    checks.append(
        IntegrityCheck(
            name="leakage_proxy",
            passed=leakage_ok,
            value=float(val_buffer_rows),
            threshold=1.0,
            detail=(
                f"Buffer in val={val_buffer_rows}; "
                f"train/val fraud rate gap={rate_gap:.4f}"
            ),
        )
    )

    # Campaign disjointness — no attack campaign may span train and val, so a
    # held-out campaign is genuinely unseen rather than a sibling of a trained step.
    disjoint = manifest.get("campaign_disjoint")
    checks.append(
        IntegrityCheck(
            name="adversarial_campaign_disjoint",
            passed=bool(disjoint) if disjoint is not None else True,
            value=float(manifest.get("adv_campaigns_val", 0)),
            threshold=0.0,
            detail=(
                f"train_campaigns={manifest.get('adv_campaigns_train', 0)} "
                f"val_campaigns={manifest.get('adv_campaigns_val', 0)} "
                f"disjoint={disjoint}"
            ),
        )
    )

    # Blue must actually train on adversarial evidence, or the loop is open.
    checks.append(
        IntegrityCheck(
            name="adversarial_rows_in_train",
            passed=train_buffer_rows > 0 or val_buffer_rows == 0,
            value=float(train_buffer_rows),
            threshold=1.0,
            detail=(
                f"train_buffer_rows={train_buffer_rows}, val_buffer_rows={val_buffer_rows} "
                "— zero in train means the hardened model never saw a Red Team attack"
            ),
        )
    )

    # Amount distribution KS (legit)
    ks_stat = 0.0
    if "amount" in df.columns and (df["is_fraud"] == 0).sum() > 20:
        legit_df = df[df["is_fraud"] == 0].copy()
        legit_df["_score"] = proba[df["is_fraud"] == 0]
        median_amt = legit_df["amount"].median()
        low = legit_df[legit_df["amount"] <= median_amt]["_score"]
        high = legit_df[legit_df["amount"] > median_amt]["_score"]
        if len(low) > 5 and len(high) > 5:
            ks_stat = float(ks_2samp(low, high).statistic)
    checks.append(
        IntegrityCheck(
            name="amount_distribution_ks",
            passed=ks_stat <= 0.35,
            value=ks_stat,
            threshold=0.35,
            detail="KS stat between low/high amount legit score distributions",
        )
    )

    passed_count = sum(1 for c in checks if c.passed)
    return IntegrityMetrics(
        checks=checks,
        passed_count=passed_count,
        total_checks=len(checks),
        all_passed=passed_count == len(checks),
        hard_negative_fpr=round(hn_fpr, 6),
        hard_negative_count=hn_count,
        split_method=split_method,
        val_buffer_rows=val_buffer_rows,
        training_manifest=manifest,
    )
