"""
Full Red↔Blue loop runner — reusable service for CLI, API, and scheduler.
"""

from __future__ import annotations

import io
import os
import sys
import uuid
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .config import get_settings
from .database import SessionLocal, init_db
from .models import CampaignEvent, LoopRun


@dataclass
class LoopRunConfig:
    families: int = 8
    skip_train_v1: bool = True
    swap_model: bool = True
    fresh_buffer: bool = True
    trigger: str = "manual"
    run_id: Optional[str] = None
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None


@dataclass
class LoopRunResult:
    run_id: str
    status: str
    kb_stats: Dict[str, Any] = field(default_factory=dict)
    buffer_stats: Dict[str, Any] = field(default_factory=dict)
    hardening: Dict[str, Any] = field(default_factory=dict)
    comparison: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    failure_analysis: Dict[str, Any] = field(default_factory=dict)
    verify: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    log: str = ""
    error: Optional[str] = None


class LoopRunner:
    """Execute the full KB → Red → Sandbox → Buffer → Harden → Verify pipeline."""

    def __init__(self):
        self.settings = get_settings()
        self._configure_env()

    def _configure_env(self) -> None:
        os.environ.setdefault("RED_TEAM_USE_LLM", "false" if not self.settings.red_team_use_llm else "true")
        if self.settings.llm_provider:
            os.environ.setdefault("LLM_PROVIDER", self.settings.llm_provider)
        if self.settings.red_team_llm_model:
            os.environ.setdefault("RED_TEAM_LLM_MODEL", self.settings.red_team_llm_model)
        if self.settings.cohere_api_key:
            os.environ.setdefault("COHERE_API_KEY", self.settings.cohere_api_key)
        os.environ.setdefault("USE_KB_API", "false")
        os.environ.setdefault("EVIDENCE_BUFFER_ENABLED", "true")
        os.environ.setdefault("FRAUDSHIELD_ENABLED", "true")
        os.environ.setdefault("EVIDENCE_BUFFER_PATH", self.settings.evidence_buffer_path)
        os.environ.setdefault("FRAUDSHIELD_MODEL_DIR", self.settings.fraudshield_model_dir)

    def run(self, config: LoopRunConfig) -> LoopRunResult:
        init_db()
        run_id = config.run_id or str(uuid.uuid4())
        session = SessionLocal()
        loop_row = LoopRun(
            id=run_id,
            status="running",
            trigger=config.trigger,
            families_count=config.families,
            skip_train_v1=config.skip_train_v1,
            swap_model=config.swap_model,
            fresh_buffer=config.fresh_buffer,
        )
        session.add(loop_row)
        session.commit()

        log_buffer = io.StringIO()
        events: List[Dict[str, Any]] = []
        result = LoopRunResult(run_id=run_id, status="running")

        try:
            with redirect_stdout(log_buffer):
                result.kb_stats = self._step_kb()
                self._step_train_v1(skip=config.skip_train_v1)
                buffer_stats, campaign_events = self._step_red_team(
                    families=config.families,
                    fresh_buffer=config.fresh_buffer,
                    run_id=run_id,
                    on_event=config.on_event,
                )
                result.buffer_stats = buffer_stats
                events = campaign_events
                hardening, comparison = self._step_harden(swap=config.swap_model)
                result.hardening = hardening
                result.comparison = comparison
                result.evaluation = self._step_evaluation(
                    run_id=run_id,
                    buffer_stats=result.buffer_stats,
                )
                result.failure_analysis = result.evaluation.get("failure_analysis", {})
                result.verify = self._step_verify()

            result.status = "completed"
            result.events = events
            result.log = log_buffer.getvalue()
            self._persist_success(session, loop_row, result, events)
        except Exception as exc:
            result.status = "failed"
            result.error = str(exc)
            result.log = log_buffer.getvalue()
            loop_row.status = "failed"
            loop_row.error_message = str(exc)
            loop_row.finished_at = datetime.now(timezone.utc)
            loop_row.log_summary = result.log[-4000:] if result.log else None
            session.commit()
        finally:
            session.close()

        return result

    def _persist_success(
        self,
        session,
        loop_row: LoopRun,
        result: LoopRunResult,
        events: List[Dict[str, Any]],
    ) -> None:
        buffer = result.buffer_stats
        comp = result.comparison
        hardening = result.hardening
        verify = result.verify
        evaluation = result.evaluation

        loop_row.status = "completed"
        loop_row.finished_at = datetime.now(timezone.utc)
        loop_row.buffer_payments = buffer.get("payment_records", 0)
        loop_row.buffer_bypassed = buffer.get("bypassed", 0)
        loop_row.buffer_blocked = buffer.get("blocked", 0)
        loop_row.families_tested = ", ".join(buffer.get("families", []))
        loop_row.v1_buffer_mean = comp.get("v1_buffer_mean_score")
        loop_row.v2_buffer_mean = comp.get("v3_buffer_mean_score", comp.get("v2_buffer_mean_score"))
        loop_row.score_lift = comp.get("buffer_score_lift")
        loop_row.recommend_swap = comp.get("recommend_swap")
        det = hardening.get("detection", {})
        loop_row.val_pr_auc = det.get("pr_auc", hardening.get("val_pr_auc"))
        loop_row.val_roc_auc = det.get("roc_auc", hardening.get("val_roc_auc"))
        loop_row.verify_decision = verify.get("decision")
        loop_row.verify_ml_score = verify.get("ml_score")
        loop_row.log_summary = result.log[-4000:] if result.log else None

        eval_path = evaluation.get("report_path")
        if eval_path:
            loop_row.log_summary = (
                (loop_row.log_summary or "")
                + f"\n[evaluation] {eval_path}"
            )[-4000:]

        for ev in events:
            session.add(
                CampaignEvent(
                    loop_run_id=loop_row.id,
                    family_id=ev["family_id"],
                    family_name=ev.get("family_name", ""),
                    step=ev.get("step"),
                    sandbox_decision=ev.get("sandbox_decision", ""),
                    evasion_outcome=ev.get("evasion_outcome", ""),
                    ml_score=ev.get("ml_score"),
                    amount=ev.get("amount"),
                )
            )
        session.commit()

    def _step_kb(self) -> Dict[str, Any]:
        from backend.red_team.agent_helpers import OfflineKnowledge

        kb = OfflineKnowledge()
        return kb.kb_stats()

    def _step_train_v1(self, skip: bool) -> None:
        spec = os.path.join(self.settings.fraudshield_model_dir, "features.json")
        if skip and os.path.exists(spec):
            print(f"  Skipped v1 training — {spec} exists")
            return
        import subprocess

        root = self._project_root()
        r = subprocess.run(
            [sys.executable, "src/scripts/train_model.py"],
            cwd=root,
        )
        if r.returncode != 0:
            raise RuntimeError("FraudShield v1 training failed")

    def _step_red_team(
        self,
        families: int,
        fresh_buffer: bool,
        run_id: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        os.environ.setdefault("RED_TEAM_LINEAR_RETRIES", "3")
        os.environ.setdefault("RED_TEAM_USE_ATTACK_ENGINE", "true")
        os.environ.setdefault("RED_TEAM_ENGINE_EXECUTE_ALL", "true")
        os.environ.setdefault("RED_TEAM_ENGINE_MAX_VARIATIONS", "20")
        os.environ.setdefault("RED_TEAM_MUTATE_BEFORE_JUMP", "2")
        os.environ.setdefault("RED_TEAM_HARD_NEGATIVES", "true")
        os.environ.setdefault("RED_TEAM_HARD_NEGATIVE_COUNT", "5")

        from backend.red_team.runner import run_red_team_for_loop
        from backend.blue_team.collector import EvidenceCollector
        from backend.blue_team.evidence_buffer import EvidenceBuffer

        buffer_path = os.environ["EVIDENCE_BUFFER_PATH"]
        if fresh_buffer and os.path.exists(buffer_path):
            os.remove(buffer_path)

        buffer = EvidenceBuffer(buffer_path)
        collector = EvidenceCollector(buffer=buffer)

        result = run_red_team_for_loop(
            families=families,
            collector=collector,
            run_id=run_id,
            on_event=on_event,
            print_sections=True,
        )
        campaign_events = result["campaign_events"]

        stats = buffer.stats()
        stats["control_gap_report"] = result.get("control_gap_report", {})
        stats["memory_entries"] = result.get("memory_entries", 0)
        stats["hard_negatives"] = result.get("hard_negatives", {})
        stats["campaign_summaries"] = result.get("summaries", [])

        print(
            f"  Memory entries: {stats['memory_entries']} | "
            f"Control gaps: {stats['control_gap_report'].get('control_gaps', 0)} | "
            f"Hard negatives: {stats['hard_negatives'].get('hard_negatives_generated', 0)}"
        )

        return stats, campaign_events

    def _step_harden(self, swap: bool) -> tuple[Dict[str, Any], Dict[str, Any]]:
        from backend.blue_team.trainer import HardeningTrainer
        from backend.blue_team.evaluator import HardeningEvaluator

        trainer = HardeningTrainer()
        print("\n--- Training FraudShield v3 (stacked ensemble + anomaly) ---")
        report = trainer.train_v3(n_baseline_legit=4000, n_baseline_fraud=4000)

        evaluator = HardeningEvaluator(
            model_dir=self.settings.fraudshield_model_dir,
            buffer_path=self.settings.evidence_buffer_path,
        )
        v1 = evaluator.load_model_version("v1")
        v3 = evaluator.load_model_version("v3")
        comparison: Dict[str, Any] = {
            "before_version": "v1",
            "after_version": "v3",
            "val_pr_auc": report.get("detection", {}).get("pr_auc"),
        }
        if v1 and v3:
            buffer_eval = evaluator.evaluate_buffer(v1, v3)
            comparison.update({
                "v1_buffer_mean_score": buffer_eval.get("v1_mean_score", 0.0),
                "v3_buffer_mean_score": buffer_eval.get("v2_mean_score", 0.0),
                "buffer_score_lift": buffer_eval.get("lift", 0.0),
                "recommend_swap": buffer_eval.get("lift", 0.0) >= 0,
                "buffer": buffer_eval,
            })
            print(
                f"  v1 buffer mean: {comparison['v1_buffer_mean_score']:.4f} "
                f"-> v3: {comparison['v3_buffer_mean_score']:.4f} "
                f"(lift {comparison['buffer_score_lift']:+.4f})"
            )

        if swap:
            trainer.swap_to_v3()
            print("  Active model swapped to v3")

        return report, comparison

    def _step_evaluation(
        self,
        run_id: str,
        buffer_stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Phase 11–14 — full evaluation, graph eval, and failure analysis."""
        from backend.blue_team.evaluation_runner import EvaluationRunner
        from backend.labs.failure_analysis import run_failure_analysis_for_loop

        eval_dir = os.path.join(self._project_root(), "data", "evaluation")
        os.makedirs(eval_dir, exist_ok=True)
        report_path = os.path.join(eval_dir, f"loop_{run_id}.json")
        failure_path = os.path.join(eval_dir, f"failure_analysis_{run_id}.json")

        buffer_stats = buffer_stats or {}
        failure_report = run_failure_analysis_for_loop(
            buffer_path=self.settings.evidence_buffer_path,
            control_gap_report=buffer_stats.get("control_gap_report"),
            campaign_summaries=buffer_stats.get("campaign_summaries"),
            model_dir=self.settings.fraudshield_model_dir,
            before_version="v1",
            after_version="v3",
        )
        with open(failure_path, "w") as f:
            import json
            json.dump(failure_report, f, indent=2)

        runner = EvaluationRunner(
            model_dir=self.settings.fraudshield_model_dir,
            buffer_path=self.settings.evidence_buffer_path,
        )
        models_report = os.path.join(
            self.settings.fraudshield_model_dir, "evaluation_report.json"
        )
        report = runner.run(
            before_version="v1",
            after_version="v3",
            n_baseline_legit=2000,
            n_baseline_fraud=2000,
            save_path=models_report,
            failure_analysis=failure_report,
        )
        import shutil
        shutil.copy(models_report, report_path)
        summary = report.summary
        asr = report.asr
        graph = report.graph_model

        print("\n--- Phase 11-14 Evaluation ---")
        print(f"  Integrity:       {summary.get('integrity_score')}")
        print(f"  Holdout PR-AUC:  {summary.get('primary_detection_metric', 0):.4f}")
        print(f"  ASR reduction:   {asr.asr_reduction:.4f} (ML {asr.before_ml_asr:.4f} -> {asr.after_ml_asr:.4f})")
        print(f"  Graph recall +Δ: {graph.graph_recall_lift:.4f}  clusters={graph.clusters_detected}")
        print(f"  CTL gap controls:{len(failure_report.get('gap_summary', {}).get('controls_with_gaps', []))}")
        print(f"  Report:          {report_path}")

        return {
            "report_path": report_path,
            "failure_analysis_path": failure_path,
            "failure_analysis": failure_report,
            "summary": summary,
            "asr": asr.model_dump(),
            "graph_fidelity": report.graph_fidelity.model_dump(),
            "graph_model": graph.model_dump(),
            "integrity_passed": report.integrity.all_passed,
            "detection": {
                "holdout_pr_auc": report.detection.after_holdout_pr_auc,
                "buffer_recall_lift": report.detection.buffer_recall_lift,
            },
            "generalization": {
                "mean_family_recall": report.generalization.mean_family_recall,
                "composite_campaigns": report.generalization.composite_campaign_count,
            },
        }

    def _step_verify(self) -> Dict[str, Any]:
        from backend.sandbox import PaymentSandbox
        from backend.blue_team.fraudshield import load_fraudshield

        model = load_fraudshield()
        sandbox = PaymentSandbox()
        sandbox.add_customer("C_loop", "Loop Test", "PAN999", "1990-01-01", "City", trust_score=0.55)
        sandbox.add_device("D_loop", "C_loop")

        result = sandbox.process_transaction({
            "transaction_id": "T_loop_verify",
            "customer_id": "C_loop",
            "device_id": "D_loop",
            "amount": 35000,
            "payment_rail": "upi",
            "authentication_method": "otp",
            "merchant_risk_score": 0.4,
        })
        state = result.get("state", {})
        return {
            "model_version": model.version if model else None,
            "model_type": model.model_type if model else None,
            "threshold": model.threshold if model else None,
            "decision": result.get("decision"),
            "reason": result.get("reason"),
            "ml_score": state.get("ml_score"),
            "rule_risk": state.get("rule_risk"),
            "risk_score": state.get("risk_score"),
            "control_triggers": state.get("control_triggers") or result.get("control_triggers") or [],
            "journey": [s.get("step") for s in result.get("journey", [])],
        }

    @staticmethod
    def _project_root() -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
