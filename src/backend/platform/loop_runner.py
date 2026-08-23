"""
Full Red↔Blue loop runner — reusable service for CLI, API, and scheduler.
"""

from __future__ import annotations

import io
import json
import os
import sys
import uuid
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .config import get_settings
from .database import SessionLocal, init_db
from .journey import snapshot_state
from .models import Campaign, CampaignEvent, LoopRun, ModelVersion, Observation


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
    campaigns: List[Dict[str, Any]] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    log: str = ""
    error: Optional[str] = None


class LoopRunner:
    """Execute the full KB → Red → Sandbox → Buffer → Harden → Verify pipeline."""

    def __init__(self):
        self.settings = get_settings()
        self._last_campaigns: List[Dict[str, Any]] = []
        self._last_observations: List[Dict[str, Any]] = []
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
                result.campaigns = self._last_campaigns
                result.observations = self._last_observations
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
            result.campaigns = self._last_campaigns
            result.observations = self._last_observations
            result.events = events
            loop_row.status = "failed"
            loop_row.error_message = str(exc)
            loop_row.finished_at = datetime.now(timezone.utc)
            loop_row.log_summary = result.log[-4000:] if result.log else None
            loop_row.buffer_payments = result.buffer_stats.get("payment_records", 0)
            loop_row.buffer_bypassed = result.buffer_stats.get("bypassed", 0)
            loop_row.buffer_blocked = result.buffer_stats.get("blocked", 0)
            # Attack evidence is still valid even when hardening fails.
            self._persist_evidence(session, loop_row, result, events)
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

        buffer_stats = hardening.get("buffer_stats", {}) or {}

        # The trainer always writes its artifact as "v2"; lineage in the UI needs a
        # monotonic label, so number rounds from the pre-hardening baseline (v1).
        rounds = session.query(ModelVersion).count()
        if rounds == 0:
            session.add(
                ModelVersion(
                    loop_run_id=loop_row.id,
                    version="v1",
                    model_type="LightGBM",
                    parent_version=None,
                    baseline_rows=hardening.get("baseline_sample", 0),
                    buffer_rows=0,
                    buffer_mean_score=comp.get("v1_buffer_mean_score"),
                    baseline_fraud_recall=comp.get("v1_baseline_fraud_recall"),
                    promoted=False,
                    report_json=json.dumps({"note": "pre-hardening baseline"}),
                )
            )
            rounds = 1

        session.add(
            ModelVersion(
                loop_run_id=loop_row.id,
                version=f"v{rounds + 1}",
                model_type="LightGBM",
                parent_version=f"v{rounds}",
                baseline_rows=hardening.get("baseline_sample", 0),
                buffer_rows=hardening.get("buffer_rows", 0),
                buffer_families=", ".join(buffer_stats.get("families", []) or []),
                feature_count=self._spec_feature_count(hardening.get("spec_path")),
                decision_threshold=hardening.get("decision_threshold"),
                val_pr_auc=hardening.get("val_pr_auc"),
                val_roc_auc=hardening.get("val_roc_auc"),
                buffer_mean_score=comp.get("v2_buffer_mean_score"),
                score_lift=comp.get("buffer_score_lift"),
                baseline_fraud_recall=comp.get("v2_baseline_fraud_recall"),
                promoted=bool(loop_row.swap_model),
                report_json=json.dumps({"hardening": hardening, "comparison": comp}, default=str),
            )
        )

        self._persist_evidence(session, loop_row, result, events)

    def _persist_evidence(
        self,
        session,
        loop_row: LoopRun,
        result: LoopRunResult,
        events: List[Dict[str, Any]],
    ) -> None:
        """Write campaigns, observations and events. Safe to call on failure paths."""
        for c in result.campaigns:
            session.merge(
                Campaign(
                    id=c["id"],
                    loop_run_id=c["loop_run_id"],
                    family_id=c["family_id"],
                    family_name=c["family_name"],
                    lifecycle_stage=c["lifecycle_stage"],
                    objective=c["objective"],
                    selected_variant=c["selected_variant"],
                    novelty_score=c["novelty_score"],
                    success_probability=c["success_probability"],
                    hypothesis_json=json.dumps(c["hypothesis"], default=str),
                    plan_json=json.dumps(c["plan"], default=str),
                    payloads_json=json.dumps(c["payloads"], default=str),
                    memory_json=json.dumps(c["memory"], default=str),
                    steps_total=c["steps_total"],
                    steps_bypassed=c["steps_bypassed"],
                    steps_blocked=c["steps_blocked"],
                    outcome=c["outcome"],
                )
            )

        for o in result.observations:
            session.add(
                Observation(
                    loop_run_id=o["loop_run_id"],
                    campaign_id=o["campaign_id"],
                    family_id=o["family_id"],
                    family_name=o["family_name"],
                    transaction_id=o["transaction_id"],
                    step=o["step"],
                    action_type=o["action_type"],
                    target_control=o["target_control"],
                    expected_outcome=o["expected_outcome"],
                    decision=o["decision"],
                    reason=o["reason"],
                    evasion_outcome=o["evasion_outcome"],
                    blocking_control=o["blocking_control"],
                    ml_score=o["ml_score"],
                    rule_risk=o["rule_risk"],
                    risk_score=o["risk_score"],
                    amount=o["amount"],
                    payment_rail=o["payment_rail"],
                    location_region=o["location_region"],
                    control_triggers_json=json.dumps(o["control_triggers"], default=str),
                    journey_json=json.dumps(o["journey"], default=str),
                    state_before_json=json.dumps(o["state_before"], default=str),
                    state_after_json=json.dumps(o["state_after"], default=str),
                    payload_json=json.dumps(o["payload"], default=str),
                    features_json=json.dumps(o["features"], default=str),
                    analysis_json=json.dumps(o["analysis"], default=str),
                )
            )

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
        from backend.red_team.agent_helpers import OfflineKnowledge
        from backend.red_team.agents.threat_hunter import ThreatHunter
        from backend.red_team.agents.attack_planner import AttackPlanner
        from backend.red_team.agents.attack_generator import AttackGenerator
        from backend.red_team.agents.failure_analyzer import FailureAnalyzer
        from backend.red_team.sandbox_client import SandboxClient
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

        from backend.red_team.agents.memory_agent import MemoryAgent

        memory_agent = MemoryAgent()

        simulatable = kb.get_simulatable_families()[:families]
        campaign_events: List[Dict[str, Any]] = []
        campaign_rows: List[Dict[str, Any]] = []
        observation_rows: List[Dict[str, Any]] = []

        for i, family in enumerate(simulatable, 1):
            family_id = family["attack_id"]
            family_name = family.get("name", "")[:80]
            print(f"\n  Campaign {i}/{len(simulatable)}: {family_id} — {family_name[:50]}")

            hypothesis = hunter.hypothesis_from_family(family)
            plan = planner.plan(hypothesis)
            sequence = generator.generate_sequence(plan)

            campaign_id = sequence.campaign_id
            memories_before = len(memory_agent.memories)
            bypassed = blocked = 0

            for payload in sequence.payloads:
                payload_dict = payload.model_dump()
                action_payload = payload_dict.get("action_payload") or {}

                sandbox = client.get_sandbox()
                state_before = snapshot_state(sandbox, action_payload)
                response = client.execute_payload(payload_dict)
                state_after = snapshot_state(sandbox, action_payload)

                analysis = analyzer.analyze(response, payload, plan)
                memory_agent.store_analysis(analysis, hypothesis, {"campaign_id": campaign_id})
                record = collector.collect(
                    response, payload, plan, hypothesis, analysis, sandbox
                )

                decision = response.get("decision", "UNKNOWN")
                evasion = (
                    record.evasion_outcome
                    if record
                    else {"ALLOW": "bypassed", "CHALLENGE": "challenged", "BLOCK": "blocked"}.get(
                        decision, "unknown"
                    )
                )
                sandbox_state = response.get("state") or {}

                observation_rows.append({
                    "loop_run_id": run_id,
                    "campaign_id": campaign_id,
                    "family_id": family_id,
                    "family_name": family_name,
                    "transaction_id": response.get("transaction_id"),
                    "step": payload_dict.get("step"),
                    "action_type": payload_dict.get("action_type", ""),
                    "target_control": payload_dict.get("target_control", ""),
                    "expected_outcome": payload_dict.get("expected_outcome", ""),
                    "decision": decision,
                    "reason": response.get("reason", ""),
                    "evasion_outcome": evasion,
                    "blocking_control": getattr(analysis, "blocking_control", None),
                    "ml_score": sandbox_state.get("ml_score"),
                    "rule_risk": sandbox_state.get("rule_risk"),
                    "risk_score": sandbox_state.get("risk_score"),
                    "amount": action_payload.get("amount"),
                    "payment_rail": action_payload.get("payment_rail", ""),
                    "location_region": action_payload.get("location_region")
                    or (record.features.get("location_region", "") if record else ""),
                    "control_triggers": response.get("control_triggers") or [],
                    "journey": response.get("journey") or [],
                    "state_before": state_before,
                    "state_after": state_after,
                    "payload": payload_dict,
                    "features": (record.features if record else {}),
                    "analysis": analysis.model_dump() if hasattr(analysis, "model_dump") else {},
                })

                if not record:
                    continue

                if record.evasion_outcome == "bypassed":
                    bypassed += 1
                else:
                    blocked += 1

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
                    f"    payment step {record.step}: {record.sandbox_decision} "
                    f"({record.evasion_outcome}) ml={record.ml_score}"
                )

            campaign_rows.append({
                "id": campaign_id,
                "loop_run_id": run_id,
                "family_id": family_id,
                "family_name": family_name,
                "lifecycle_stage": family.get("lifecycle_stage", ""),
                "objective": plan.objective,
                "selected_variant": plan.selected_variant,
                "novelty_score": hypothesis.novelty_score,
                "success_probability": hypothesis.success_probability,
                "hypothesis": hypothesis.model_dump(),
                "plan": plan.model_dump(),
                "payloads": [p.model_dump() for p in sequence.payloads],
                "memory": [
                    m.model_dump() for m in memory_agent.memories[memories_before:]
                ],
                "steps_total": len(sequence.payloads),
                "steps_bypassed": bypassed,
                "steps_blocked": blocked,
                "outcome": "bypassed" if bypassed else "contained",
            })

        self._last_campaigns = campaign_rows
        self._last_observations = observation_rows

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
    def _spec_feature_count(spec_path: Optional[str]) -> int:
        if not spec_path or not os.path.exists(spec_path):
            return 0
        try:
            with open(spec_path) as f:
                return len(json.load(f).get("feature_order", []))
        except Exception:
            return 0

    @staticmethod
    def _project_root() -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
