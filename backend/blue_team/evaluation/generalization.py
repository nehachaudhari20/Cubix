"""
Phase 11c — Generalization: LOFO, unseen family/variant, composite campaigns.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set

import numpy as np

from ..metrics import evaluate_detection
from ..schemas import (  # noqa: F401
    SurfaceRecall,
    CompositeCampaignMetrics,
    FamilyRecall,
    GeneralizationMetrics,
    LOFOMetrics,
    VariantRecall,
)
from .context import EvaluationContext


def _trained_families(ctx: EvaluationContext, all_families: Set[str]) -> Set[str]:
    manifest = ctx.manifest
    families = set(manifest.get("buffer_stats", {}).get("families", []))
    if not families:
        sources = manifest.get("training_sources", {})
        if sources.get("buffer_families"):
            families = set(sources["buffer_families"])
    return families or set(all_families)


def run_generalization_suite(ctx: EvaluationContext) -> GeneralizationMetrics:
    # All adjudicated surfaces, not payment only — otherwise agent, auth_se, kyc,
    # consent, device and network attacks are invisible to the generalization
    # pillar even though Blue now trains on them.
    records = ctx.attack_records()
    if not records:
        return GeneralizationMetrics()

    model = ctx.after
    families = sorted({r.attack_family for r in records})
    train_families = _trained_families(ctx, set(families))

    family_rows: List[FamilyRecall] = []
    lofo_rows: List[LOFOMetrics] = []

    for family in families:
        subset = [r for r in records if r.attack_family == family]
        scores = ctx.score_records(subset, model)
        y = np.ones(len(scores), dtype=int)
        det = evaluate_detection(f"family_{family}", y, scores, threshold=model.threshold)
        family_rows.append(
            FamilyRecall(
                family=family,
                samples=len(scores),
                recall=round(det.recall, 6),
                mean_score=round(float(np.mean(scores)), 6) if scores else 0.0,
            )
        )

        # LOFO: score held-out family vs in-training families proxy
        held_out = subset
        in_train = [r for r in records if r.attack_family != family]
        ho_scores = ctx.score_records(held_out, model)
        tr_scores = ctx.score_records(in_train, model) if in_train else []
        ho_det = evaluate_detection(
            f"lofo_{family}",
            np.ones(len(ho_scores), dtype=int),
            ho_scores,
            threshold=model.threshold,
        )
        tr_recall = (
            float(np.mean(np.asarray(tr_scores) >= model.threshold))
            if tr_scores
            else 0.0
        )
        lofo_rows.append(
            LOFOMetrics(
                held_out_family=family,
                held_out_samples=len(ho_scores),
                held_out_recall=round(ho_det.recall, 6),
                train_proxy_samples=len(tr_scores),
                train_proxy_recall=round(tr_recall, 6),
                recall_gap=round(ho_det.recall - tr_recall, 6),
            )
        )

    recalls = [fr.recall for fr in family_rows]
    unseen_families = [fr for fr in family_rows if fr.family not in train_families]
    seen_families = [fr for fr in family_rows if fr.family in train_families]

    # Unseen variants
    variant_rows: List[VariantRecall] = []
    by_variant: Dict[str, List] = defaultdict(list)
    for r in records:
        key = r.attack_variant or "default"
        by_variant[key].append(r)

    train_variants = {
        r.attack_variant or "default"
        for r in ctx.evaluator.buffer.read_all()
        if r.attack_family in train_families
    }
    for variant, subset in sorted(by_variant.items()):
        scores = ctx.score_records(subset, model)
        det = evaluate_detection(
            f"variant_{variant}",
            np.ones(len(scores), dtype=int),
            scores,
            threshold=model.threshold,
        )
        variant_rows.append(
            VariantRecall(
                variant=variant,
                samples=len(scores),
                recall=round(det.recall, 6),
                mean_score=round(float(np.mean(scores)), 6) if scores else 0.0,
                is_unseen=variant not in train_variants and variant != "default",
            )
        )

    unseen_variants = [v for v in variant_rows if v.is_unseen]

    # Composite campaigns (multi-step / multi-family)
    by_campaign: Dict[str, List] = defaultdict(list)
    for r in records:
        by_campaign[r.campaign_id].append(r)

    composite_rows: List[CompositeCampaignMetrics] = []
    for campaign_id, steps in by_campaign.items():
        families_in_camp = sorted({s.attack_family for s in steps})
        scores = ctx.score_records(steps, model)
        det = evaluate_detection(
            f"campaign_{campaign_id[:8]}",
            np.ones(len(scores), dtype=int),
            scores,
            threshold=model.threshold,
        )
        bypassed = sum(
            1 for s in steps
            if s.evasion_outcome == "bypassed" or s.sandbox_decision == "ALLOW"
        )
        composite_rows.append(
            CompositeCampaignMetrics(
                campaign_id=campaign_id,
                steps=len(steps),
                families=families_in_camp,
                is_composite=len(families_in_camp) > 1 or len(steps) > 1,
                recall=round(det.recall, 6),
                mean_score=round(float(np.mean(scores)), 6) if scores else 0.0,
                bypass_rate=round(bypassed / len(steps), 6) if steps else 0.0,
            )
        )

    composite_only = [c for c in composite_rows if c.is_composite]
    lofo_gaps = [r.recall_gap for r in lofo_rows]

    # Per-surface recall — a headline number hides that the model may detect
    # payment fraud well and agent or consent abuse not at all.
    surface_rows: List[SurfaceRecall] = []
    for surface in sorted({r.surface for r in records}):
        subset = [r for r in records if r.surface == surface]
        scores = ctx.score_records(subset, model)
        if not scores:
            continue
        det = evaluate_detection(
            f"surface_{surface}",
            np.ones(len(scores), dtype=int),
            scores,
            threshold=model.threshold,
        )
        bypassed = sum(
            1 for r in subset
            if r.sandbox_decision == "ALLOW" or r.evasion_outcome == "bypassed"
        )
        surface_rows.append(
            SurfaceRecall(
                surface=surface,
                samples=len(subset),
                recall=round(det.recall, 6),
                mean_score=round(float(np.mean(scores)), 6),
                sandbox_bypass_rate=round(bypassed / len(subset), 6),
            )
        )

    return GeneralizationMetrics(
        surface_recall=surface_rows,
        mean_surface_recall=round(
            float(np.mean([s.recall for s in surface_rows])), 6
        ) if surface_rows else 0.0,
        min_surface_recall=round(
            float(np.min([s.recall for s in surface_rows])), 6
        ) if surface_rows else 0.0,
        buffer_families=families,
        trained_families=sorted(train_families),
        family_recall=family_rows,
        mean_family_recall=round(float(np.mean(recalls)), 6) if recalls else 0.0,
        min_family_recall=round(float(np.min(recalls)), 6) if recalls else 0.0,
        unseen_family_count=len(unseen_families),
        unseen_family_recall=round(
            float(np.mean([f.recall for f in unseen_families])), 6
        ) if unseen_families else 0.0,
        seen_family_recall=round(
            float(np.mean([f.recall for f in seen_families])), 6
        ) if seen_families else 0.0,
        lofo=lofo_rows,
        mean_lofo_gap=round(float(np.mean(lofo_gaps)), 6) if lofo_gaps else 0.0,
        variant_recall=variant_rows,
        unseen_variant_count=len(unseen_variants),
        unseen_variant_recall=round(
            float(np.mean([v.recall for v in unseen_variants])), 6
        ) if unseen_variants else 0.0,
        composite_campaigns=composite_rows,
        composite_campaign_count=len(composite_only),
        composite_mean_recall=round(
            float(np.mean([c.recall for c in composite_only])), 6
        ) if composite_only else 0.0,
    )
