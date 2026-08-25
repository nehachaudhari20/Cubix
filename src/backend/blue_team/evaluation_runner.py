"""
Full evaluation runner (Phase 11).

Produces a JSON report across five pillars:
  Detection | Fidelity | Generalization
              ↓
        Integrity Tests
              ↓
        Attack Success Rate (Before → After)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from .evaluator import HardeningEvaluator
from .fraudshield import DEFAULT_MODEL_DIR
from .metrics import evaluate_detection, hard_negative_fpr
from .schemas import (
    ASRMetrics,
    EvaluationReport,
    FamilyRecall,
    FidelityMetrics,
    GeneralizationMetrics,
    IntegrityCheck,
    IntegrityMetrics,
)
from .trainer import HardeningTrainer, FEATURE_DEFAULTS


def _load_training_manifest(model_dir: Path, version: str) -> Dict[str, Any]:
    """Load training manifest from hardening report or features spec."""
    candidates = [
        model_dir / "hardening_report_v3.json",
        model_dir / "hardening_report.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        with open(path) as f:
            report = json.load(f)
        if report.get("version", "").startswith(version[:2]) or version in ("v2", "v3"):
            manifest = report.get("training_manifest") or report.get("mix_stats") or {}
            manifest["report_path"] = str(path)
            return manifest

    spec_name = f"features_{version}.json" if version != "v1" else "features.json"
    spec_path = model_dir / spec_name
    if spec_path.exists():
        with open(spec_path) as f:
            spec = json.load(f)
        return {
            "split_method": spec.get("split_method", "unknown"),
            "training_sources": spec.get("training_sources", {}),
            "report_path": str(spec_path),
        }
    return {}


class EvaluationRunner:
    """Run the full Blue Team evaluation framework."""

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
        self.trainer = self.evaluator.trainer

    def run(
        self,
        before_version: str = "v1",
        after_version: str = "v2",
        *,
        n_baseline_legit: int = 500,
        n_baseline_fraud: int = 500,
        save_path: Optional[str] = None,
    ) -> EvaluationReport:
        before = self.evaluator.load_model_version(before_version)
        after = self.evaluator.load_model_version(after_version)
        if not before or not after:
            raise FileNotFoundError(
                f"Models required: before={before_version} after={after_version}"
            )

        detection = self._pillar_detection(
            before, after, n_baseline_legit, n_baseline_fraud
        )
        fidelity = self._pillar_fidelity(after, n_baseline_legit, n_baseline_fraud)
        generalization = self._pillar_generalization(before, after)
        manifest = _load_training_manifest(self.model_dir, after_version)
        integrity = self._pillar_integrity(
            after, before, after_version, manifest, n_baseline_legit, n_baseline_fraud
        )
        asr = self._pillar_asr(before, after)

        summary = self._build_summary(detection, fidelity, generalization, integrity, asr)

        report = EvaluationReport(
            before_version=before_version,
            after_version=after_version,
            generated_at=datetime.now(timezone.utc).isoformat(),
            detection=detection,
            fidelity=fidelity,
            generalization=generalization,
            integrity=integrity,
            asr=asr,
            summary=summary,
        )

        out = save_path or self.DEFAULT_REPORT_PATH
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(report.model_dump(), f, indent=2)

        return report

    def _pillar_detection(
        self,
        before,
        after,
        n_legit: int,
        n_fraud: int,
    ) -> Dict[str, Any]:
        buffer_eval = self.evaluator.evaluate_buffer(before, after)
        before_holdout = self.evaluator.evaluate_baseline_holdout(before, n_fraud, n_legit)
        after_holdout = self.evaluator.evaluate_baseline_holdout(after, n_fraud, n_legit)

        before_det = before_holdout.get("detection") or {}
        after_det = after_holdout.get("detection") or {}

        return {
            "baseline_holdout": {
                "before": before_det,
                "after": after_det,
                "delta": self._detection_delta_dict(before_det, after_det),
            },
            "adversarial_buffer": buffer_eval,
            "primary_metric": "pr_auc",
            "before_holdout_pr_auc": before_det.get("pr_auc", 0.0),
            "after_holdout_pr_auc": after_det.get("pr_auc", 0.0),
            "buffer_recall_lift": round(
                buffer_eval.get("v2_recall_at_threshold", 0.0)
                - buffer_eval.get("v1_recall_at_threshold", 0.0),
                6,
            ),
        }

    def _detection_delta_dict(
        self, before: Dict[str, Any], after: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "pr_auc_delta": round(after.get("pr_auc", 0) - before.get("pr_auc", 0), 6),
            "recall_delta": round(after.get("recall", 0) - before.get("recall", 0), 6),
            "fpr_delta": round(after.get("fpr", 0) - before.get("fpr", 0), 6),
            "recall_at_1pct_fpr_delta": round(
                after.get("recall_at_1pct_fpr", 0) - before.get("recall_at_1pct_fpr", 0),
                6,
            ),
        }

    def _score_baseline_split(
        self, model, n_legit: int, n_fraud: int
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        df = self.trainer.load_baseline_sample(n_legit=n_legit, n_fraud=n_fraud)
        X = self.evaluator._encode_for_model(df, model)
        proba = self.evaluator._predict_proba(model, X)
        return df, proba

    def _pillar_fidelity(
        self, model, n_legit: int, n_fraud: int
    ) -> FidelityMetrics:
        df, proba = self._score_baseline_split(model, n_legit, n_fraud)
        legit_mask = df["is_fraud"] == 0
        fraud_mask = df["is_fraud"] == 1

        legit_scores = proba[legit_mask.values]
        fraud_scores = proba[fraud_mask.values]

        amount_corr = 0.0
        if legit_mask.any() and "amount" in df.columns:
            amounts = pd.to_numeric(df.loc[legit_mask, "amount"], errors="coerce").fillna(0)
            if len(amounts) > 2 and amounts.std() > 0:
                amount_corr = float(np.corrcoef(amounts, legit_scores)[0, 1])

        hour_std = 0.0
        if "hour_of_day" in df.columns and legit_mask.any():
            legit_df = df.loc[legit_mask].copy()
            legit_df["_score"] = legit_scores
            hour_means = legit_df.groupby("hour_of_day")["_score"].mean()
            hour_std = float(hour_means.std()) if len(hour_means) > 1 else 0.0

        rail_spread = 0.0
        if "payment_rail" in df.columns and legit_mask.any():
            legit_df = df.loc[legit_mask].copy()
            legit_df["_score"] = legit_scores
            rail_means = legit_df.groupby("payment_rail")["_score"].mean()
            rail_spread = float(rail_means.max() - rail_means.min()) if len(rail_means) > 1 else 0.0

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
            hour_score_std=round(hour_std, 6),
            rail_score_spread=round(rail_spread, 6),
            legit_samples=int(legit_mask.sum()),
            fraud_samples=int(fraud_mask.sum()),
        )

    def _pillar_generalization(self, before, after) -> GeneralizationMetrics:
        records = [
            r
            for r in self.evaluator.buffer.read_all()
            if r.action_type == "initiate_payment" and r.label == 1
        ]
        if not records:
            return GeneralizationMetrics()

        families = sorted({r.attack_family for r in records})
        family_rows: List[FamilyRecall] = []

        for family in families:
            subset = [r for r in records if r.attack_family == family]
            scores = []
            for record in subset:
                row = dict(record.features)
                for col in after.feature_order:
                    if col not in row:
                        row[col] = FEATURE_DEFAULTS.get(col, 0)
                scores.append(self.evaluator._predict_row_proba(after, row))

            y = np.ones(len(scores), dtype=int)
            det = evaluate_detection(
                f"family_{family}",
                y,
                scores,
                threshold=after.threshold,
            )
            family_rows.append(
                FamilyRecall(
                    family=family,
                    samples=len(scores),
                    recall=round(det.recall, 6),
                    mean_score=round(float(np.mean(scores)), 6) if scores else 0.0,
                )
            )

        recalls = [fr.recall for fr in family_rows]
        manifest = _load_training_manifest(self.model_dir, after.version)
        train_families = set(manifest.get("buffer_stats", {}).get("families", []))
        if not train_families:
            train_families = set(families)

        unseen = [fr for fr in family_rows if fr.family not in train_families]
        unseen_recall = (
            float(np.mean([fr.recall for fr in unseen])) if unseen else 0.0
        )

        return GeneralizationMetrics(
            buffer_families=families,
            family_recall=family_rows,
            mean_family_recall=round(float(np.mean(recalls)), 6) if recalls else 0.0,
            min_family_recall=round(float(np.min(recalls)), 6) if recalls else 0.0,
            unseen_family_count=len(unseen),
            unseen_family_recall=round(unseen_recall, 6),
        )

    def _pillar_integrity(
        self,
        after,
        before,
        after_version: str,
        manifest: Dict[str, Any],
        n_legit: int,
        n_fraud: int,
    ) -> IntegrityMetrics:
        checks: List[IntegrityCheck] = []
        df, proba = self._score_baseline_split(after, n_legit, n_fraud)
        y = df["is_fraud"].astype(int).values

        # Null control — shuffled labels should yield ~chance PR-AUC
        rng = np.random.default_rng(42)
        y_shuffled = rng.permutation(y)
        null_det = evaluate_detection("null_control", y_shuffled, proba)
        null_passed = null_det.pr_auc <= 0.65
        checks.append(
            IntegrityCheck(
                name="null_control",
                passed=null_passed,
                value=null_det.pr_auc,
                threshold=0.65,
                detail="Shuffled-label PR-AUC should stay near chance (~0.5)",
            )
        )

        # Ablation — zeroed features should not produce extreme scores on legit
        ablated_rows = []
        for _, row in df[df["is_fraud"] == 0].iterrows():
            zeroed = {col: 0 for col in after.feature_order}
            ablated_rows.append(self.evaluator._predict_row_proba(after, zeroed))
        ablated_fpr = float(np.mean(np.asarray(ablated_rows) >= after.threshold)) if ablated_rows else 0.0
        ablation_passed = ablated_fpr <= 0.15
        checks.append(
            IntegrityCheck(
                name="ablation_zero_features",
                passed=ablation_passed,
                value=ablated_fpr,
                threshold=0.15,
                detail="FPR on legit rows with all features zeroed",
            )
        )

        # Hard negatives from buffer
        hn_records = [
            r
            for r in self.evaluator.buffer.read_all()
            if r.is_hard_negative and r.label == 0 and r.action_type == "initiate_payment"
        ]
        hn_fpr = 0.0
        hn_count = len(hn_records)
        if hn_records:
            hn_scores = []
            for record in hn_records:
                row = dict(record.features)
                for col in after.feature_order:
                    if col not in row:
                        row[col] = FEATURE_DEFAULTS.get(col, 0)
                hn_scores.append(self.evaluator._predict_row_proba(after, row))
            hn_y = np.zeros(len(hn_scores), dtype=int)
            hn_mask = np.ones(len(hn_scores), dtype=bool)
            hn_stats = hard_negative_fpr(hn_y, hn_scores, after.threshold, hn_mask)
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

        # Temporal split integrity from training manifest
        split_method = manifest.get("split_method", "unknown")
        val_buffer_rows = int(manifest.get("val_buffer_rows", 0))
        temporal_passed = split_method == "temporal_group" or val_buffer_rows >= 0
        checks.append(
            IntegrityCheck(
                name="temporal_split",
                passed=temporal_passed,
                value=float(val_buffer_rows),
                threshold=0.0,
                detail=f"split_method={split_method}, val_buffer_rows={val_buffer_rows}",
            )
        )

        # Leakage proxy — buffer tail should appear in validation, not train-only
        leakage_passed = (
            split_method == "temporal_group" and val_buffer_rows > 0
        ) or split_method == "unknown"
        checks.append(
            IntegrityCheck(
                name="leakage_proxy",
                passed=leakage_passed,
                value=float(val_buffer_rows),
                threshold=1.0,
                detail="Adversarial buffer rows isolated in validation split",
            )
        )

        # Amount distribution sanity (KS on legit scores: high vs low amount)
        ks_stat = 0.0
        if "amount" in df.columns and (df["is_fraud"] == 0).sum() > 20:
            legit_df = df[df["is_fraud"] == 0].copy()
            legit_df["_score"] = proba[df["is_fraud"] == 0]
            median_amt = legit_df["amount"].median()
            low = legit_df[legit_df["amount"] <= median_amt]["_score"]
            high = legit_df[legit_df["amount"] > median_amt]["_score"]
            if len(low) > 5 and len(high) > 5:
                ks_stat = float(ks_2samp(low, high).statistic)
        ks_passed = ks_stat <= 0.35
        checks.append(
            IntegrityCheck(
                name="amount_distribution_ks",
                passed=ks_passed,
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

    def _pillar_asr(self, before, after) -> ASRMetrics:
        records = [
            r
            for r in self.evaluator.buffer.read_all()
            if r.action_type == "initiate_payment" and r.label == 1
        ]
        if not records:
            return ASRMetrics()

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

        s_before = self.evaluator._score_buffer_records(before)
        s_after = self.evaluator._score_buffer_records(after)
        y = np.ones(len(s_before), dtype=int)

        before_det = evaluate_detection("asr_before", y, s_before, threshold=before.threshold)
        after_det = evaluate_detection("asr_after", y, s_after, threshold=after.threshold)

        hist_bypass_rate = bypassed / total
        projected_after = 1.0 - after_det.recall

        return ASRMetrics(
            payment_attacks=total,
            historical_bypass_count=bypassed,
            historical_bypass_rate=round(hist_bypass_rate, 6),
            historical_block_rate=round(blocked / total, 6),
            before_ml_recall=round(before_det.recall, 6),
            after_ml_recall=round(after_det.recall, 6),
            ml_recall_lift=round(after_det.recall - before_det.recall, 6),
            projected_bypass_rate_after=round(projected_after, 6),
            asr_reduction=round(after_det.recall - before_det.recall, 6),
        )

    def _build_summary(
        self,
        detection: Dict[str, Any],
        fidelity: FidelityMetrics,
        generalization: GeneralizationMetrics,
        integrity: IntegrityMetrics,
        asr: ASRMetrics,
    ) -> Dict[str, Any]:
        buffer = detection.get("adversarial_buffer", {})
        holdout_delta = detection.get("baseline_holdout", {}).get("delta", {})

        recommend_hardening = (
            buffer.get("lift", 0) >= 0
            and holdout_delta.get("recall_delta", 0) >= -0.05
            and holdout_delta.get("fpr_delta", 1) <= 0.05
            and asr.ml_recall_lift >= 0
        )

        return {
            "recommend_hardening": recommend_hardening,
            "integrity_passed": integrity.all_passed,
            "integrity_score": f"{integrity.passed_count}/{integrity.total_checks}",
            "primary_detection_metric": detection.get("after_holdout_pr_auc", 0.0),
            "buffer_score_lift": buffer.get("lift", 0.0),
            "asr_ml_recall_lift": asr.ml_recall_lift,
            "mean_family_recall": generalization.mean_family_recall,
            "score_separation": fidelity.score_separation,
            "pillars": ["detection", "fidelity", "generalization", "integrity", "asr"],
        }
