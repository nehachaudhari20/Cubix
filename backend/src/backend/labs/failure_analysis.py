"""
Phase 12 — Failure analysis aggregation.

Combines adversarial buffer, control-gap lab, Red Team campaign summaries,
and ASR evaluation into a gap report with CTL-* heatmap and per-family ASR.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from backend.blue_team.schemas import ASRMetrics, EvidenceRecord, FamilyASR
from backend.sandbox.rules.control_implementations import build_trigger_map


def resolve_trigger_to_ctl(trigger: str) -> str:
    """Map sandbox trigger or CTL id to canonical CTL-* control id."""
    if not trigger:
        return "UNKNOWN"
    if trigger.startswith("CTL-"):
        return trigger
    prefix_map = build_trigger_map()
    for prefix, control_id in prefix_map.items():
        if trigger == prefix or trigger.startswith(prefix):
            return control_id
    return trigger


class FailureAnalysisAggregator:
    """Aggregate Red Team failures, control gaps, and ML ASR into one report."""

    def aggregate(
        self,
        *,
        buffer_records: Iterable[EvidenceRecord],
        control_gap_report: Optional[Dict[str, Any]] = None,
        campaign_summaries: Optional[List[Dict[str, Any]]] = None,
        asr_metrics: Optional[ASRMetrics] = None,
        before_version: str = "v1",
        after_version: str = "v3",
    ) -> Dict[str, Any]:
        records = [
            r for r in buffer_records
            if r.action_type == "initiate_payment" and r.label == 1
        ]
        gap_report = control_gap_report or {}
        summaries = campaign_summaries or []

        ctl_heatmap = self._build_ctl_heatmap(records, gap_report)
        per_family = self._build_per_family_asr(records, asr_metrics, summaries)
        red_eval = self._build_red_eval_summary(records, summaries, gap_report)
        gap_summary = self._build_gap_summary(gap_report, ctl_heatmap)

        top_gaps = sorted(
            ctl_heatmap.items(),
            key=lambda kv: (-kv[1]["gap_count"], -kv[1]["miss_count"], kv[0]),
        )[:10]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "before_version": before_version,
            "after_version": after_version,
            "payment_attacks": len(records),
            "gap_summary": gap_summary,
            "ctl_heatmap": ctl_heatmap,
            "top_ctl_gaps": [
                {"control_id": cid, **stats} for cid, stats in top_gaps
            ],
            "per_family_asr": per_family,
            "red_eval": red_eval,
            "asr_overall": self._asr_overall_block(asr_metrics),
        }

    def _build_ctl_heatmap(
        self,
        records: List[EvidenceRecord],
        gap_report: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        heatmap: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "triggered_count": 0,
                "gap_count": 0,
                "miss_count": 0,
                "bypass_with_trigger": 0,
                "bypass_without_trigger": 0,
                "families_triggered": defaultdict(int),
                "families_missed": defaultdict(int),
                "families_gapped": defaultdict(int),
            }
        )

        for record in records:
            bypassed = (
                record.evasion_outcome == "bypassed"
                or record.sandbox_decision == "ALLOW"
            )
            triggers = {resolve_trigger_to_ctl(t) for t in (record.control_triggers or [])}

            for ctl in triggers:
                cell = heatmap[ctl]
                cell["triggered_count"] += 1
                cell["families_triggered"][record.attack_family] += 1
                if bypassed:
                    cell["bypass_with_trigger"] += 1

            if bypassed and not triggers:
                cell = heatmap["NO_CONTROL_FIRED"]
                cell["miss_count"] += 1
                cell["families_missed"][record.attack_family] += 1

            if record.blocking_control:
                ctl = resolve_trigger_to_ctl(record.blocking_control)
                if bypassed:
                    heatmap[ctl]["miss_count"] += 1
                    heatmap[ctl]["families_missed"][record.attack_family] += 1

        for finding in gap_report.get("findings", []):
            for missing in finding.get("missing_control_ids") or []:
                ctl = resolve_trigger_to_ctl(missing)
                cell = heatmap[ctl]
                cell["gap_count"] += 1
                expected = finding.get("expected_control_ids") or []
                for exp in expected:
                    if resolve_trigger_to_ctl(exp) == ctl:
                        cell["families_gapped"]["expected"] += 1

        for expected in gap_report.get("unique_missing_controls") or []:
            ctl = resolve_trigger_to_ctl(expected)
            heatmap[ctl]["gap_count"] = max(heatmap[ctl]["gap_count"], 1)

        normalized: Dict[str, Dict[str, Any]] = {}
        for ctl, raw in heatmap.items():
            normalized[ctl] = {
                "triggered_count": raw["triggered_count"],
                "gap_count": raw["gap_count"],
                "miss_count": raw["miss_count"],
                "bypass_with_trigger": raw["bypass_with_trigger"],
                "bypass_without_trigger": raw["bypass_without_trigger"],
                "families_triggered": dict(raw["families_triggered"]),
                "families_missed": dict(raw["families_missed"]),
                "families_gapped": dict(raw["families_gapped"]),
            }
        return normalized

    def _build_per_family_asr(
        self,
        records: List[EvidenceRecord],
        asr_metrics: Optional[ASRMetrics],
        summaries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_family: Dict[str, List[EvidenceRecord]] = defaultdict(list)
        for r in records:
            by_family[r.attack_family].append(r)

        asr_by_family: Dict[str, FamilyASR] = {}
        if asr_metrics:
            asr_by_family = {f.family: f for f in asr_metrics.per_family}

        summary_by_family = {s.get("family_id"): s for s in summaries if s.get("family_id")}

        rows: List[Dict[str, Any]] = []
        for family in sorted(by_family.keys()):
            subset = by_family[family]
            bypassed = sum(
                1 for r in subset
                if r.evasion_outcome == "bypassed" or r.sandbox_decision == "ALLOW"
            )
            blocked = len(subset) - bypassed
            asr_row = asr_by_family.get(family)
            camp = summary_by_family.get(family, {})

            ctl_triggers: Dict[str, int] = defaultdict(int)
            for r in subset:
                for t in r.control_triggers or []:
                    ctl_triggers[resolve_trigger_to_ctl(t)] += 1

            rows.append({
                "family": family,
                "attacks": len(subset),
                "sandbox_bypassed": bypassed,
                "sandbox_blocked": blocked,
                "historical_bypass_rate": round(bypassed / len(subset), 6) if subset else 0.0,
                "before_ml_recall": asr_row.before_ml_recall if asr_row else 0.0,
                "after_ml_recall": asr_row.after_ml_recall if asr_row else 0.0,
                "before_ml_asr": round(1 - asr_row.before_ml_recall, 6) if asr_row else 0.0,
                "after_ml_asr": round(1 - asr_row.after_ml_recall, 6) if asr_row else 0.0,
                "asr_reduction": asr_row.asr_reduction if asr_row else 0.0,
                "control_gaps_in_campaign": camp.get("control_gaps", 0),
                "steps_executed": camp.get("steps_executed", len(subset)),
                "top_ctl_triggers": sorted(
                    ctl_triggers.items(), key=lambda x: -x[1]
                )[:5],
            })
        return rows

    def _build_red_eval_summary(
        self,
        records: List[EvidenceRecord],
        summaries: List[Dict[str, Any]],
        gap_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        bypassed = sum(
            1 for r in records
            if r.evasion_outcome == "bypassed" or r.sandbox_decision == "ALLOW"
        )
        families_tested = sorted({r.attack_family for r in records})
        linear_retries = sum(s.get("linear_retries_used", 0) for s in summaries)
        total_gaps = sum(s.get("control_gaps", 0) for s in summaries)

        blocking_controls: Dict[str, int] = defaultdict(int)
        for r in records:
            if r.blocking_control:
                blocking_controls[r.blocking_control] += 1

        return {
            "families_tested": families_tested,
            "campaign_count": len(summaries),
            "total_steps": sum(s.get("steps_executed", 0) for s in summaries) or len(records),
            "linear_retries_used": linear_retries,
            "sandbox_bypass_count": bypassed,
            "sandbox_bypass_rate": round(bypassed / len(records), 6) if records else 0.0,
            "control_gaps_detected": gap_report.get("control_gaps", total_gaps),
            "unique_missing_controls": gap_report.get("unique_missing_controls", []),
            "blocking_control_breakdown": dict(blocking_controls),
            "outcomes_by_family": {
                s.get("family_id"): {
                    "successes": (s.get("outcomes") or []).count("success"),
                    "failures": (s.get("outcomes") or []).count("failure"),
                    "final_decision": s.get("final_decision"),
                }
                for s in summaries
            },
        }

    def _build_gap_summary(
        self,
        gap_report: Dict[str, Any],
        ctl_heatmap: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        gap_controls: Set[str] = set()
        for ctl, cell in ctl_heatmap.items():
            if cell["gap_count"] > 0 or cell["miss_count"] > 0:
                gap_controls.add(ctl)

        return {
            "total_findings": gap_report.get("total_findings", 0),
            "control_gaps": gap_report.get("control_gaps", len(gap_controls)),
            "unique_missing_controls": gap_report.get(
                "unique_missing_controls",
                sorted(c for c in gap_controls if c.startswith("CTL-")),
            ),
            "controls_with_misses": sorted(
                c for c, cell in ctl_heatmap.items() if cell["miss_count"] > 0
            ),
            "controls_with_gaps": sorted(
                c for c, cell in ctl_heatmap.items() if cell["gap_count"] > 0
            ),
        }

    @staticmethod
    def _asr_overall_block(asr_metrics: Optional[ASRMetrics]) -> Dict[str, Any]:
        if not asr_metrics:
            return {}
        return {
            "payment_attacks": asr_metrics.payment_attacks,
            "historical_bypass_rate": asr_metrics.historical_bypass_rate,
            "before_ml_asr": asr_metrics.before_ml_asr,
            "after_ml_asr": asr_metrics.after_ml_asr,
            "asr_reduction": asr_metrics.asr_reduction,
            "before_ml_recall": asr_metrics.before_ml_recall,
            "after_ml_recall": asr_metrics.after_ml_recall,
            "ml_recall_lift": asr_metrics.ml_recall_lift,
        }


def run_failure_analysis_for_loop(
    *,
    buffer_path: str,
    control_gap_report: Optional[Dict[str, Any]] = None,
    campaign_summaries: Optional[List[Dict[str, Any]]] = None,
    model_dir: str = "data/models",
    before_version: str = "v1",
    after_version: str = "v3",
) -> Dict[str, Any]:
    """Entry point for loop_runner — loads buffer + ASR then aggregates."""
    from pathlib import Path

    from backend.blue_team.evaluation.asr import run_asr_for_loop
    from backend.blue_team.evidence_buffer import EvidenceBuffer

    buffer = EvidenceBuffer(buffer_path)
    records = buffer.read_all()

    asr_dict = run_asr_for_loop(
        model_dir=model_dir,
        buffer_path=buffer_path,
        before_version=before_version,
        after_version=after_version,
    )

    from backend.blue_team.schemas import ASRMetrics, FamilyASR

    asr_metrics = ASRMetrics(
        payment_attacks=asr_dict.get("payment_attacks", 0),
        historical_bypass_rate=asr_dict.get("historical_bypass_rate", 0.0),
        before_ml_asr=asr_dict.get("before_ml_asr", 0.0),
        after_ml_asr=asr_dict.get("after_ml_asr", 0.0),
        asr_reduction=asr_dict.get("asr_reduction", 0.0),
        before_ml_recall=asr_dict.get("before_ml_recall", 0.0),
        after_ml_recall=asr_dict.get("after_ml_recall", 0.0),
        ml_recall_lift=asr_dict.get("ml_recall_lift", 0.0),
        per_family=[
            FamilyASR(**row) for row in asr_dict.get("per_family", [])
        ],
    )

    aggregator = FailureAnalysisAggregator()
    return aggregator.aggregate(
        buffer_records=records,
        control_gap_report=control_gap_report,
        campaign_summaries=campaign_summaries,
        asr_metrics=asr_metrics,
        before_version=before_version,
        after_version=after_version,
    )
