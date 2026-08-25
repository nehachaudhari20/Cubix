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
    families: int = 5
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

        loop_row.status = "completed"
        loop_row.finished_at = datetime.now(timezone.utc)
        loop_row.buffer_payments = buffer.get("payment_records", 0)
        loop_row.buffer_bypassed = buffer.get("bypassed", 0)
        loop_row.buffer_blocked = buffer.get("blocked", 0)
        loop_row.families_tested = ", ".join(buffer.get("families", []))
        loop_row.v1_buffer_mean = comp.get("v1_buffer_mean_score")
        loop_row.v2_buffer_mean = comp.get("v2_buffer_mean_score")
        loop_row.score_lift = comp.get("buffer_score_lift")
        loop_row.recommend_swap = comp.get("recommend_swap")
        loop_row.val_pr_auc = hardening.get("val_pr_auc")
        loop_row.val_roc_auc = hardening.get("val_roc_auc")
        loop_row.verify_decision = verify.get("decision")
        loop_row.verify_ml_score = verify.get("ml_score")
        loop_row.log_summary = result.log[-4000:] if result.log else None

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
        os.environ.setdefault("RED_TEAM_LINEAR_RETRIES", "2")
        os.environ.setdefault("RED_TEAM_USE_ATTACK_ENGINE", "true")

        from backend.red_team.runner import select_families, _linear_retry_limit
        from backend.red_team.agent_helpers import OfflineKnowledge
        from backend.red_team.agents.threat_hunter import ThreatHunter
        from backend.red_team.agents.attack_planner import AttackPlanner
        from backend.red_team.agents.attack_generator import AttackGenerator
        from backend.red_team.agents.failure_analyzer import FailureAnalyzer
        from backend.red_team.sandbox_client import SandboxClient
        from backend.red_team.deepteam.linear_mutator import LinearMutator
        from backend.blue_team.collector import EvidenceCollector
        from backend.blue_team.evidence_buffer import EvidenceBuffer

        buffer_path = os.environ["EVIDENCE_BUFFER_PATH"]
        if fresh_buffer and os.path.exists(buffer_path):
            os.remove(buffer_path)

        buffer = EvidenceBuffer(buffer_path)
        collector = EvidenceCollector(buffer=buffer)
        client = SandboxClient()
        kb = OfflineKnowledge()

        hunter = ThreatHunter()
        planner = AttackPlanner()
        generator = AttackGenerator()
        analyzer = FailureAnalyzer()
        mutator = LinearMutator()

        selected = select_families(kb, max_families=families)
        campaign_events: List[Dict[str, Any]] = []

        print(
            f"  CVSS-ordered {len(selected)} families | "
            f"strategy={os.environ.get('RED_TEAM_JAILBREAK_STRATEGY', 'kb')} | "
            f"linear_retries={_linear_retry_limit()}"
        )

        for i, family in enumerate(selected, 1):
            family_id = family["attack_id"]
            family_name = family.get("name", "")[:80]
            print(f"\n  Campaign {i}/{len(selected)}: {family_id} - {family_name[:50]}")

            hypothesis = hunter.hypothesis_from_family(family)
            hypothesis.jailbreak_strategy = os.environ.get("RED_TEAM_JAILBREAK_STRATEGY", "kb")
            plan = planner.plan(hypothesis)
            sequence = generator.generate_sequence(plan)

            linear_limit = _linear_retry_limit()
            for payload in sequence.payloads:
                payloads_to_run = [payload]
                for current in payloads_to_run:
                    response = client.execute_payload(current.model_dump())
                    analysis = analyzer.analyze(response, current, plan)
                    record = collector.collect(
                        response, current, plan, hypothesis, analysis, client.get_sandbox()
                    )
                    if record:
                        event = {
                            "loop_run_id": run_id,
                            "family_id": family_id,
                            "family_name": family_name,
                            "step": record.step,
                            "sandbox_decision": record.sandbox_decision,
                            "evasion_outcome": record.evasion_outcome,
                            "ml_score": record.ml_score,
                            "amount": record.amount,
                        }
                        campaign_events.append(event)
                        if on_event:
                            on_event(event)
                        print(
                            f"    step {record.step}: {record.sandbox_decision} "
                            f"({record.evasion_outcome}) ml={record.ml_score}"
                        )

                    if (
                        current.action_type == "initiate_payment"
                        and analysis.outcome == "failure"
                        and linear_limit > 0
                    ):
                        for attempt in range(linear_limit):
                            mutated = mutator.mutate(current, analysis, attempt=attempt)
                            response = client.execute_payload(mutated.model_dump())
                            analysis = analyzer.analyze(response, mutated, plan)
                            record = collector.collect(
                                response, mutated, plan, hypothesis, analysis, client.get_sandbox()
                            )
                            if record:
                                event = {
                                    "loop_run_id": run_id,
                                    "family_id": family_id,
                                    "family_name": family_name,
                                    "step": record.step,
                                    "sandbox_decision": record.sandbox_decision,
                                    "evasion_outcome": record.evasion_outcome,
                                    "ml_score": record.ml_score,
                                    "amount": record.amount,
                                }
                                campaign_events.append(event)
                                if on_event:
                                    on_event(event)
                                print(
                                    f"    step {record.step} (linear): {record.sandbox_decision} "
                                    f"({record.evasion_outcome}) ml={record.ml_score}"
                                )
                            if analysis.outcome == "success":
                                break

        return buffer.stats(), campaign_events

    def _step_harden(self, swap: bool) -> tuple[Dict[str, Any], Dict[str, Any]]:
        from backend.blue_team.trainer import HardeningTrainer
        from backend.blue_team.evaluator import HardeningEvaluator

        trainer = HardeningTrainer()
        report = trainer.train_v2(n_baseline_legit=4000, n_baseline_fraud=4000)
        comparison_obj = HardeningEvaluator().full_report()
        comparison = comparison_obj.model_dump()

        if swap:
            trainer.swap_to_v2()

        return report, comparison

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
