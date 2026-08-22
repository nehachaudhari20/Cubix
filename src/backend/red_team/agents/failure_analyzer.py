"""
Failure Analyzer Agent — attributes sandbox outcomes to KB controls and signals.
"""

import json
from typing import Any, Dict, List, Optional

from ..schemas import AnalysisResult, AttackPlan, ActionPayload
from ..agent_helpers import OfflineKnowledge, get_llm, USE_LLM
from ..kb_campaign_builder import match_triggers_to_kb_signals


class FailureAnalyzer:
    """Parses real sandbox observations and maps them back to KB signals."""

    def __init__(self, model_name: str = None):
        self.kb = OfflineKnowledge()
        self.llm = get_llm()

    def analyze(
        self,
        sandbox_response: Dict[str, Any],
        payload: ActionPayload,
        plan: AttackPlan,
    ) -> AnalysisResult:
        rule_result = self._analyze_rule_based(sandbox_response, payload, plan)

        if self.llm and USE_LLM:
            llm_result = self._enhance_with_llm(sandbox_response, payload, plan, rule_result)
            if llm_result:
                return llm_result

        return rule_result

    def _analyze_rule_based(
        self,
        sandbox_response: Dict[str, Any],
        payload: ActionPayload,
        plan: AttackPlan,
    ) -> AnalysisResult:
        decision = sandbox_response.get("decision", "UNKNOWN")
        reason = sandbox_response.get("reason", "unknown")
        journey = sandbox_response.get("journey", [])
        state = sandbox_response.get("state", {})
        control_triggers = sandbox_response.get("control_triggers") or state.get("control_triggers") or []

        if payload.action_type != "initiate_payment":
            outcome = "success" if decision in ("PASS", "ALLOW") else "failure"
        else:
            outcome = "success" if decision == "ALLOW" else "failure"

        blocking_control, blocking_reason = self._find_blocking_step(journey, reason, control_triggers)
        risk_score = state.get("risk_score") or sandbox_response.get("risk_score")

        family = self.kb.get_family(plan.primary_family) or {}
        kb_signals = match_triggers_to_kb_signals(
            control_triggers, family, self.kb.signals
        )

        learnings = self._build_learnings(
            outcome, blocking_control, blocking_reason,
            control_triggers, kb_signals, risk_score, payload, plan,
        )
        mutations = self._build_mutations(
            outcome, blocking_control, blocking_reason,
            control_triggers, kb_signals, payload, plan, family,
        )

        return AnalysisResult(
            outcome=outcome,
            blocking_control=blocking_control,
            blocking_reason=blocking_reason,
            risk_score=risk_score,
            learnings=learnings,
            mutation_suggestions=mutations,
            confidence=0.9,
            journey_trace=journey,
        )

    def _find_blocking_step(
        self, journey: List[Dict], reason: str, control_triggers: List[str]
    ) -> tuple:
        for step in journey:
            step_name = step.get("step", "")
            result = step.get("result", {})

            if step_name == "KYC" and result.get("status") == "FAIL":
                return "KYC", result.get("reason", reason)
            if step_name == "Authentication" and result.get("status") == "FAIL":
                return "Authentication", "auth_failed"
            if step_name == "Payment Initiation" and result.get("status") == "FAIL":
                return "Payment Initiation", result.get("reason", reason)
            if step_name == "Authorization":
                if result.get("decision") in ("BLOCK", "CHALLENGE"):
                    return "Authorization", result.get("reason", reason)
            if step_name == "Risk":
                rules = result.get("rule_details") or []
                triggered = []
                for r in rules:
                    triggered.extend(r.get("triggered_rules") or [])
                if triggered:
                    return "Risk", f"Rules: {', '.join(triggered[:3])}"

        if control_triggers:
            return "Risk", f"Controls: {', '.join(control_triggers[:3])}"
        if "velocity" in reason:
            return "Authorization", reason
        if "kyc" in reason:
            return "KYC", reason
        return "Authorization", reason

    def _build_learnings(
        self, outcome, blocking_control, blocking_reason,
        triggers, kb_signals, risk_score, payload, plan,
    ) -> List[str]:
        learnings = [
            f"[{plan.primary_family}] Action {payload.action_type} → {outcome.upper()}",
            f"Target control: {payload.target_control}",
        ]
        if blocking_control:
            learnings.append(f"Blocked at {blocking_control}: {blocking_reason}")
        if triggers:
            learnings.append(f"Sandbox triggers: {', '.join(triggers)}")
        if kb_signals:
            learnings.append(f"KB signals matched: {', '.join(kb_signals)}")
        if risk_score is not None:
            learnings.append(f"Risk score: {risk_score}")
        return learnings

    def _build_mutations(
        self, outcome, blocking_control, blocking_reason,
        triggers, kb_signals, payload, plan, family,
    ) -> List[str]:
        mutations = []
        controls = family.get("controls_targeted") or []

        if outcome == "success":
            mutations.append("Increase amount toward next KB signal threshold")
            if controls:
                mutations.append(f"Probe adjacent control: {controls[0]}")
            return mutations[:4]

        if kb_signals:
            mutations.append(f"Adjust payload to evade KB signal: {kb_signals[0]}")

        if blocking_control == "Authorization" and "velocity" in (blocking_reason or ""):
            mutations.extend([
                "Spread transactions over longer time window",
                "Reduce per-transaction amount below velocity band",
            ])
        elif blocking_control == "Risk":
            if any("device" in t for t in triggers):
                mutations.append("Register device earlier before high-value payment")
            if any("mule" in t or "beneficiary" in t for t in triggers):
                mutations.append("Lower initial transfer to new beneficiary")
            if any("mcc" in t or "merchant" in t for t in triggers):
                mutations.append("Try lower-risk declared MCC")
            mutations.append("Reduce amount below risk tier threshold")
        elif blocking_control == "KYC":
            mutations.append("Increase trust_score or use verified customer profile")
        else:
            stage = family.get("lifecycle_stage", "")
            mutations.append(f"Mutate parameters for stage '{stage}' based on KB attack_flow")

        return mutations[:4]

    def _enhance_with_llm(
        self, sandbox_response, payload, plan, base: AnalysisResult
    ) -> Optional[AnalysisResult]:
        try:
            from langchain.schema import HumanMessage, SystemMessage
            from langchain.output_parsers import PydanticOutputParser

            parser = PydanticOutputParser(pydantic_object=AnalysisResult)
            family = self.kb.get_family(plan.primary_family)

            prompt = f"""Enhance attack analysis using KB context.

Base: {base.model_dump_json()}
Family controls: {family.get('controls_targeted') if family else []}
Family signals: {[s.get('name') for s in (family.get('detection_signals') or [])[:5]] if family else []}
Sandbox: {json.dumps(sandbox_response, indent=2)[:2500]}

{parser.get_format_instructions()}"""

            response = self.llm.invoke([
                SystemMessage(content="Return only valid JSON."),
                HumanMessage(content=prompt),
            ])
            return parser.parse(response.content)
        except Exception:
            return None
