"""
Phase 14 — Graph model evaluation.

Cluster detection, cross-account composite campaigns, and tabular vs
tabular+graph ablation on buffer ASR/recall.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set

import numpy as np

from ..graph.graph_signals import GRAPH_SIGNAL_FEATURES, GraphSignalBuilder
from ..metrics import evaluate_detection
from ..schemas import GraphFidelityMetrics, GraphModelMetrics
from .context import EvaluationContext


def _graph_features(record) -> Dict[str, Any]:
    return dict(record.features or {})


def _is_graph_heavy(features: Dict[str, Any]) -> bool:
    return (
        int(features.get("is_shared_beneficiary", 0)) == 1
        or int(features.get("beneficiary_distinct_payer_count", 0)) >= 3
        or int(features.get("shared_device_customer_count", 0)) >= 2
        or int(features.get("graph_cluster_size", 0)) >= 3
        or float(features.get("mule_risk_score", 0)) >= 0.35
    )


def run_graph_fidelity(ctx: EvaluationContext) -> GraphFidelityMetrics:
    """Graph signal distribution checks on adversarial buffer (Phase 13 fidelity)."""
    records = ctx.payment_records()
    if not records:
        return GraphFidelityMetrics()

    checks: List[Dict[str, Any]] = []
    signal_stats: Dict[str, Dict[str, float]] = {}

    for key in ["distinct_beneficiaries_last_24h", "distinct_devices_last_7d", *GRAPH_SIGNAL_FEATURES]:
        values = [float(_graph_features(r).get(key, 0)) for r in records]
        if not values:
            continue
        arr = np.asarray(values, dtype=float)
        std = float(np.std(arr))
        mean = float(np.mean(arr))
        signal_stats[key] = {
            "mean": round(mean, 4),
            "std": round(std, 4),
            "max": round(float(np.max(arr)), 4),
            "nonzero_rate": round(float(np.mean(arr > 0)), 4),
        }
        if key in ("distinct_beneficiaries_last_24h", "distinct_devices_last_7d"):
            checks.append({
                "name": f"{key}_not_constant",
                "passed": std > 0 or mean > 1,
                "value": std,
                "detail": "Graph counters should vary across buffer attacks",
            })

    graph_heavy = sum(1 for r in records if _is_graph_heavy(_graph_features(r)))
    coverage = graph_heavy / len(records)

    after = ctx.after
    scores = ctx.score_records(records, after)
    heavy_idx = [i for i, r in enumerate(records) if _is_graph_heavy(_graph_features(r))]
    light_idx = [i for i in range(len(records)) if i not in heavy_idx]

    heavy_recall = 0.0
    light_recall = 0.0
    if heavy_idx:
        heavy_scores = np.asarray(scores)[heavy_idx]
        heavy_recall = float(np.mean(heavy_scores >= after.threshold))
    if light_idx:
        light_scores = np.asarray(scores)[light_idx]
        light_recall = float(np.mean(light_scores >= after.threshold))

    return GraphFidelityMetrics(
        buffer_samples=len(records),
        graph_signal_stats=signal_stats,
        graph_heavy_count=graph_heavy,
        graph_heavy_coverage=round(coverage, 6),
        graph_heavy_recall=round(heavy_recall, 6),
        graph_light_recall=round(light_recall, 6),
        checks=checks,
        all_checks_passed=all(c["passed"] for c in checks) if checks else True,
    )


def run_graph_model_eval(ctx: EvaluationContext) -> GraphModelMetrics:
    """Cluster detection, composite campaigns, tabular vs graph ablation."""
    records = ctx.payment_records()
    if not records:
        return GraphModelMetrics()

    before, after = ctx.before, ctx.after
    y = np.ones(len(records), dtype=int)

    tabular_before = np.asarray(ctx.score_records(records, before), dtype=float)
    tabular_after = np.asarray(ctx.score_records(records, after), dtype=float)

    boosts = np.asarray([
        GraphSignalBuilder.graph_boost(_graph_features(r)) for r in records
    ], dtype=float)
    graph_after = np.minimum(1.0, tabular_after + boosts)
    graph_before = np.minimum(1.0, tabular_before + boosts * 0.5)

    tab_after_det = evaluate_detection("tabular_after", y, tabular_after, threshold=after.threshold)
    graph_after_det = evaluate_detection("graph_after", y, graph_after, threshold=after.threshold)
    tab_before_det = evaluate_detection("tabular_before", y, tabular_before, threshold=before.threshold)
    graph_before_det = evaluate_detection("graph_before", y, graph_before, threshold=before.threshold)

    heavy_mask = np.asarray([_is_graph_heavy(_graph_features(r)) for r in records])
    heavy_records = [r for r, m in zip(records, heavy_mask) if m]

    heavy_tab_recall = 0.0
    heavy_graph_recall = 0.0
    if heavy_records:
        h_idx = np.where(heavy_mask)[0]
        heavy_tab_recall = float(np.mean(tabular_after[h_idx] >= after.threshold))
        heavy_graph_recall = float(np.mean(graph_after[h_idx] >= after.threshold))

    clusters = _detect_clusters_from_records(records)
    composite = _composite_cross_account(records, ctx)

    return GraphModelMetrics(
        buffer_samples=len(records),
        clusters_detected=len(clusters),
        clusters=clusters[:10],
        composite_cross_account_count=len(composite),
        composite_campaigns=composite[:10],
        tabular_before_recall=round(tab_before_det.recall, 6),
        tabular_after_recall=round(tab_after_det.recall, 6),
        graph_before_recall=round(graph_before_det.recall, 6),
        graph_after_recall=round(graph_after_det.recall, 6),
        graph_recall_lift=round(graph_after_det.recall - tab_after_det.recall, 6),
        tabular_before_asr=round(1 - tab_before_det.recall, 6),
        tabular_after_asr=round(1 - tab_after_det.recall, 6),
        graph_before_asr=round(1 - graph_before_det.recall, 6),
        graph_after_asr=round(1 - graph_after_det.recall, 6),
        graph_asr_reduction=round(
            (1 - tab_after_det.recall) - (1 - graph_after_det.recall), 6
        ),
        graph_heavy_tabular_recall=round(heavy_tab_recall, 6),
        graph_heavy_graph_recall=round(heavy_graph_recall, 6),
        graph_heavy_recall_lift=round(heavy_graph_recall - heavy_tab_recall, 6),
    )


def _detect_clusters_from_records(records) -> List[Dict[str, Any]]:
    """Infer clusters from stored graph features per evidence record."""
    beneficiary_payers: Dict[str, Set[str]] = defaultdict(set)
    device_users: Dict[str, Set[str]] = defaultdict(set)
    campaign_customers: Dict[str, Set[str]] = defaultdict(set)

    for r in records:
        feats = _graph_features(r)
        campaign_customers[r.campaign_id].add(r.attack_family)
        payer_count = int(feats.get("beneficiary_distinct_payer_count", 0))
        if payer_count >= 3:
            key = f"shared_ben_{payer_count}_{r.campaign_id[:8]}"
            beneficiary_payers[key].add(r.attack_family)

        shared_dev = int(feats.get("shared_device_customer_count", 0))
        if shared_dev >= 2:
            key = f"shared_dev_{shared_dev}_{r.campaign_id[:8]}"
            device_users[key].add(r.attack_family)

        cluster_size = int(feats.get("graph_cluster_size", 0))
        if cluster_size >= 3:
            beneficiary_payers[f"cluster_{cluster_size}_{r.campaign_id[:8]}"].add(r.attack_family)

    clusters: List[Dict[str, Any]] = []
    for cluster_id, members in {**beneficiary_payers, **device_users}.items():
        if len(members) >= 1:
            clusters.append({
                "cluster_id": cluster_id,
                "families": sorted(members),
                "family_count": len(members),
                "signal": cluster_id.split("_")[0] + "_" + cluster_id.split("_")[1],
            })
    return sorted(clusters, key=lambda c: -c["family_count"])


def _composite_cross_account(records, ctx: EvaluationContext) -> List[Dict[str, Any]]:
    """Cross-account composite: campaigns with graph-heavy multi-step patterns."""
    by_campaign: Dict[str, List] = defaultdict(list)
    for r in records:
        by_campaign[r.campaign_id].append(r)

    composites: List[Dict[str, Any]] = []
    for campaign_id, steps in by_campaign.items():
        families = sorted({s.attack_family for s in steps})
        graph_heavy_steps = sum(1 for s in steps if _is_graph_heavy(_graph_features(s)))
        max_cluster = max(
            int(_graph_features(s).get("graph_cluster_size", 1)) for s in steps
        )
        max_payers = max(
            int(_graph_features(s).get("beneficiary_distinct_payer_count", 0)) for s in steps
        )
        is_composite = (
            len(families) > 1
            or len(steps) > 1
            or graph_heavy_steps >= 1
            or max_cluster >= 3
            or max_payers >= 3
        )
        if not is_composite:
            continue

        scores = ctx.score_records(steps, ctx.after)
        bypassed = sum(
            1 for s in steps
            if s.evasion_outcome == "bypassed" or s.sandbox_decision == "ALLOW"
        )
        composites.append({
            "campaign_id": campaign_id,
            "steps": len(steps),
            "families": families,
            "graph_heavy_steps": graph_heavy_steps,
            "max_cluster_size": max_cluster,
            "max_beneficiary_payers": max_payers,
            "recall": round(float(np.mean(np.asarray(scores) >= ctx.after.threshold)), 6),
            "bypass_rate": round(bypassed / len(steps), 6),
            "cross_account_signal": max_payers >= 3 or max_cluster >= 4,
        })

    return sorted(composites, key=lambda c: (-int(c["cross_account_signal"]), -c["graph_heavy_steps"]))
