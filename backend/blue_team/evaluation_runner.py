"""
Full evaluation runner (Phase 11 orchestrator).

Delegates to sub-pillars:
  11a detection  | 11b fidelity | 11c generalization
                 ↓
           11d integrity
                 ↓
              11e ASR
                 ↓
        13 graph fidelity | 14 graph model eval
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .evaluator import HardeningEvaluator
from .evaluation.asr import run_asr_evaluation
from .evaluation.context import EvaluationContext
from .evaluation.detection import run_detection_suite
from .evaluation.fidelity import run_fidelity_checks
from .evaluation.generalization import run_generalization_suite
from .evaluation.graph_model import run_graph_fidelity, run_graph_model_eval
from .evaluation.integrity import run_integrity_battery
from .evaluation.manifest import load_training_manifest
from .fraudshield import DEFAULT_MODEL_DIR
from .schemas import EvaluationReport

# Backward-compatible re-export
_load_training_manifest = load_training_manifest


class EvaluationRunner:
    """Run the full Blue Team evaluation framework (11a–11e)."""

    DEFAULT_REPORT_PATH = os.path.join("data", "models", "evaluation_report.json")

    def __init__(
        self,
        model_dir: str = DEFAULT_MODEL_DIR,
        buffer_path: Optional[str] = None,
    ):
        self.model_dir = Path(model_dir)
        self.evaluator = HardeningEvaluator(
            model_dir=model_dir,
            buffer_path=buffer_path or os.environ.get(
                "EVIDENCE_BUFFER_PATH",
                os.path.join("data", "adversarial_buffer", "evidence.jsonl"),
            ),
        )

    def run(
        self,
        before_version: str = "v1",
        after_version: str = "v2",
        *,
        n_baseline_legit: int = 500,
        n_baseline_fraud: int = 500,
        save_path: Optional[str] = None,
        failure_analysis: Optional[Dict[str, Any]] = None,
    ) -> EvaluationReport:
        ctx = EvaluationContext.build(
            self.evaluator,
            self.model_dir,
            before_version,
            after_version,
        )

        detection = run_detection_suite(
            ctx,
            n_baseline_legit=n_baseline_legit,
            n_baseline_fraud=n_baseline_fraud,
        )
        fidelity = run_fidelity_checks(
            ctx,
            n_baseline_legit=n_baseline_legit,
            n_baseline_fraud=n_baseline_fraud,
        )
        generalization = run_generalization_suite(ctx)
        integrity = run_integrity_battery(
            ctx,
            n_baseline_legit=n_baseline_legit,
            n_baseline_fraud=n_baseline_fraud,
        )
        asr = run_asr_evaluation(ctx)
        graph_fidelity = run_graph_fidelity(ctx)
        graph_model = run_graph_model_eval(ctx)

        summary = self._build_summary(
            detection, fidelity, generalization, integrity, asr, graph_fidelity, graph_model
        )

        report = EvaluationReport(
            before_version=before_version,
            after_version=after_version,
            generated_at=datetime.now(timezone.utc).isoformat(),
            detection=detection,
            fidelity=fidelity,
            generalization=generalization,
            integrity=integrity,
            asr=asr,
            graph_fidelity=graph_fidelity,
            graph_model=graph_model,
            failure_analysis=failure_analysis,
            summary=summary,
        )

        out = save_path or self.DEFAULT_REPORT_PATH
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(report.model_dump(), f, indent=2)

        return report

    def _build_summary(
        self, detection, fidelity, generalization, integrity, asr, graph_fidelity, graph_model
    ) -> dict:
        holdout_delta = detection.holdout.get("delta", {})
        buffer_cmp = detection.buffer.get("comparison", {})

        # Judge the loop at the matched operating point: a conservative
        # threshold on v3 must not read as "hardening failed". Fall back to the
        # native lift when no matched point could be computed.
        asr_lift = (
            asr.ml_recall_lift_matched
            if asr.matched_fpr is not None
            else asr.ml_recall_lift
        )

        # Holdout recall is also compared at a matched operating point.
        # `recall_delta` uses each model's own threshold, so a model calibrated to
        # a stricter FPR looks worse even when it ranks strictly better — the same
        # artifact that made ASR read as a regression. recall_at_1pct_fpr is
        # already a fixed-FPR metric, so it is the fair comparison; raw
        # recall_delta is only allowed to veto when FPR also got worse.
        recall_at_fpr_delta = holdout_delta.get("recall_at_1pct_fpr_delta", 0)
        fpr_delta = holdout_delta.get("fpr_delta", 1)
        recall_regressed_at_equal_fpr = recall_at_fpr_delta < -0.02

        recommend_hardening = (
            buffer_cmp.get("lift", 0) >= 0
            and not recall_regressed_at_equal_fpr
            and fpr_delta <= 0.05
            and asr_lift >= 0
        )

        return {
            "recommend_hardening": recommend_hardening,
            "hardening_gate_metric": (
                "asr_reduction_matched" if asr.matched_fpr is not None else "asr_reduction"
            ),
            "gate_detail": {
                "buffer_lift": buffer_cmp.get("lift", 0),
                "recall_at_1pct_fpr_delta": recall_at_fpr_delta,
                "recall_delta_native_threshold": holdout_delta.get("recall_delta", 0),
                "fpr_delta": fpr_delta,
                "asr_lift": asr_lift,
            },
            "integrity_passed": integrity.all_passed,
            "integrity_score": f"{integrity.passed_count}/{integrity.total_checks}",
            "fidelity_passed": fidelity.all_checks_passed,
            "primary_detection_metric": detection.after_holdout_pr_auc,
            "buffer_score_lift": buffer_cmp.get("lift", 0.0),
            "asr_ml_recall_lift": asr.ml_recall_lift,
            "asr_reduction": asr.asr_reduction,
            "before_ml_asr": asr.before_ml_asr,
            "after_ml_asr": asr.after_ml_asr,
            "asr_reduction_matched": asr.asr_reduction_matched,
            "before_ml_asr_matched": asr.before_ml_asr_matched,
            "after_ml_asr_matched": asr.after_ml_asr_matched,
            "matched_fpr": asr.matched_fpr,
            "asr_by_surface": {s.surface: s.asr_reduction for s in asr.per_surface},
            "mean_family_recall": generalization.mean_family_recall,
            "mean_surface_recall": generalization.mean_surface_recall,
            "min_surface_recall": generalization.min_surface_recall,
            "recall_by_surface": {
                s.surface: s.recall for s in generalization.surface_recall
            },
            "mean_lofo_gap": generalization.mean_lofo_gap,
            "composite_campaign_count": generalization.composite_campaign_count,
            "score_separation": fidelity.score_separation,
            "graph_heavy_coverage": graph_fidelity.graph_heavy_coverage,
            "graph_recall_lift": graph_model.graph_recall_lift,
            "graph_asr_reduction": graph_model.graph_asr_reduction,
            "composite_cross_account_count": graph_model.composite_cross_account_count,
            "pillars": {
                "11a_detection": "holdout+test+buffer",
                "11b_fidelity": "amount+timing+behavior",
                "11c_generalization": "lofo+unseen+composite",
                "11d_integrity": "leakage+null+ablation+temporal",
                "11e_asr": "before_after",
                "13_graph_fidelity": "graph_signals+buffer",
                "14_graph_model": "cluster+composite+ablation",
            },
        }
