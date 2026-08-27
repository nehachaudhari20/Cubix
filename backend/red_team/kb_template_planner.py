"""
KB Template Planner — builds AttackPlans from canonical simulation templates,
lifecycle stages, vectors, and GenAI entry points.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader
from backend.sandbox.lifecycle_router import (
    derive_entry_point,
    setup_flags_for_entry,
    stages_to_action_types,
    template_action_types,
)
from backend.taxonomy import SURFACE_ENTRY_ACTION, techniques_for_family

from .kb_campaign_builder import (
    _payment_steps,
    build_hypothesis_from_family,
    classify_family,
    derive_payload_hints,
    pick_target_control,
)
from .schemas import AttackPlan, Hypothesis, PlanStep


ACTION_LABELS = {
    "register_customer": "Register customer",
    "register_device": "Register device fingerprint",
    "verify_kyc": "Verify KYC / identity",
    "authenticate": "Authenticate session",
    "open_account": "Open account",
    "onboard_merchant": "Onboard merchant",
    "link_beneficiary": "Link beneficiary",
    "simulate_genai_context": "Manipulate AI agent context",
    "simulate_social_engineering": "Run social-engineering contact",
    "submit_kyc_evidence": "Submit identity evidence",
    "request_consent": "Request open-banking consent",
    "establish_session": "Establish device session",
    "orchestrate_network": "Orchestrate account network",
    "initiate_payment": "Initiate payment",
}


class KBTemplatePlanner:
    """Plan campaigns from KB templates instead of hardcoded setup steps."""

    def __init__(self, kb_path: str = "data/knowledge/canonical"):
        self.canonical = CanonicalKnowledgeLoader(kb_path)

    def build_plan(
        self,
        family: Dict[str, Any],
        stages: List[Dict],
        global_signals: List[Dict],
        hypothesis: Optional[Hypothesis] = None,
    ) -> AttackPlan:
        if hypothesis is None:
            hypothesis = build_hypothesis_from_family(family)

        hints = derive_payload_hints(family, global_signals)
        entry_point = derive_entry_point(family)
        setup_flags = setup_flags_for_entry(entry_point)
        hints.update({k: v for k, v in setup_flags.items() if k not in hints})

        template = self.canonical.get_template(family.get("simulation_template_id") or "")
        stage_records = self.canonical.get_family_stages(family.get("attack_id") or "")

        if entry_point == "cross_stage" and stage_records:
            action_types = stages_to_action_types(family, stage_records)
        elif template and template.get("supported_action_types"):
            action_types = template_action_types(template, entry_point)
        else:
            action_types = template_action_types(None, entry_point)

        genai_caps = (family.get("genai") or {}).get("capability_ids") or []
        steps = self._build_steps(
            family=family,
            stages=stages,
            hints=hints,
            action_types=action_types,
            entry_point=entry_point,
            genai_caps=genai_caps,
        )

        pattern = classify_family(family)
        stage_name = family.get("lifecycle_stage") or "Payment Initiation"
        return AttackPlan(
            campaign_name=family.get("name") or hypothesis.name,
            objective=(
                f"Simulate {family.get('attack_id')} ({pattern}) entry={entry_point} "
                f"via {len(steps)} KB-mapped actions"
            ),
            target_stages=[stage_name],
            primary_family=family.get("attack_id"),
            selected_variant=hypothesis.suggested_variant or (family.get("variants") or ["default"])[0],
            steps=steps,
            success_criteria=(
                "Expose target controls or complete GenAI proxy + payment observation"
            ),
            estimated_complexity="high" if len(steps) > 6 else "medium" if len(steps) > 3 else "low",
            reasoning=(
                f"{hypothesis.reasoning} Entry point={entry_point}, "
                f"template={family.get('simulation_template_id') or 'proxy'}."
            ),
            entry_point=entry_point,
        )

    def _build_steps(
        self,
        *,
        family: Dict[str, Any],
        stages: List[Dict],
        hints: Dict[str, Any],
        action_types: List[str],
        entry_point: str,
        genai_caps: List[str],
    ) -> List[PlanStep]:
        steps: List[PlanStep] = []
        step_num = 1
        payment_path = hints.get("payment_path", "full")

        for action_type in action_types:
            if action_type == "initiate_payment":
                if not any(s.action_type == "register_customer" for s in steps) and entry_point == "merchant":
                    steps.append(
                        PlanStep(
                            step=step_num,
                            action_type="register_customer",
                            action="Register payer for merchant settlement probe",
                            target_control=pick_target_control(family, stages, "register_customer"),
                            payload_template={
                                "trust_score": 0.75,
                                "verified": True,
                                "account_age_days": 180,
                                "entry_point": entry_point,
                            },
                            expected_outcome="PASS",
                            rationale="Minimal payer for merchant-originated payment",
                        )
                    )
                    step_num += 1
                    if "register_device" not in action_types:
                        steps.append(
                            PlanStep(
                                step=step_num,
                                action_type="register_device",
                                action="Register payer device",
                                target_control=pick_target_control(family, stages, "register_device"),
                                payload_template={"entry_point": entry_point},
                                expected_outcome="PASS",
                                rationale="Device for merchant payment leg",
                            )
                        )
                        step_num += 1
                payment_steps, step_num = _payment_steps(hints, family, stages, step_num)
                for ps in payment_steps:
                    ps.payload_template = {
                        **(ps.payload_template or {}),
                        "payment_path": payment_path,
                        "entry_point": entry_point,
                        "genai_features": hints.get("genai_features", {}),
                        "capability_ids": genai_caps,
                        "attack_family": family.get("attack_id"),
                    }
                steps.extend(payment_steps)
                continue

            tpl = self._template_for_action(action_type, hints, family, genai_caps, entry_point)
            steps.append(
                PlanStep(
                    step=step_num,
                    action_type=action_type,
                    action=f"{ACTION_LABELS.get(action_type, action_type)} [{family.get('attack_id')}]",
                    target_control=pick_target_control(family, stages, action_type),
                    payload_template=tpl,
                    expected_outcome="PASS",
                    rationale=f"KB entry={entry_point} action={action_type}",
                )
            )
            step_num += 1

        return steps

    @staticmethod
    def _template_for_action(
        action_type: str,
        hints: Dict[str, Any],
        family: Dict[str, Any],
        genai_caps: List[str],
        entry_point: str,
    ) -> Dict[str, Any]:
        trust = float(hints.get("trust_score", 0.65))
        base: Dict[str, Any] = {"entry_point": entry_point}

        if action_type == "register_customer":
            base.update({
                "trust_score": trust,
                "pan": hints.get("pan", "SYN0000001"),
                "verified": hints.get("verified", trust >= 0.5),
                "account_age_days": int(hints.get("account_age_days", 0)),
            })
        elif action_type == "register_device":
            base.update({"fingerprint": hints.get("fingerprint", {})})
        elif action_type == "authenticate":
            base.update({"authentication_method": hints.get("authentication_method", "otp")})
        elif action_type == "open_account":
            base.update({"balance": float(hints.get("balance", 75000))})
        elif action_type == "onboard_merchant":
            base.update({
                "mcc": hints.get("mcc", "7995"),
                "declared_mcc": hints.get("declared_mcc", "5411"),
                "risk_score": float(hints.get("merchant_risk_score", 0.35)),
                "skip_payer_setup": hints.get("skip_payer_setup", False),
            })
        elif action_type == "link_beneficiary":
            base.update({"risk_score": float(hints.get("beneficiary_risk_score", 0.25))})
        elif action_type in SURFACE_ACTIONS:
            base.update(
                _surface_payload(
                    action_type=action_type,
                    family=family,
                    hints=hints,
                    genai_caps=genai_caps,
                    entry_point=entry_point,
                )
            )

        return base


SURFACE_ACTIONS = frozenset(SURFACE_ENTRY_ACTION.values()) - {"initiate_payment"}


def _surface_payload(
    *,
    action_type: str,
    family: Dict[str, Any],
    hints: Dict[str, Any],
    genai_caps: List[str],
    entry_point: str,
) -> Dict[str, Any]:
    """
    Build the payload for a non-payment surface action.

    Shared keys first, then surface-specific attacker-controlled parameters. Values
    come from KB hints where available so the planner stays data-driven; the
    literals here are the attacker's opening move, which mutation later varies.
    """
    family_id = family.get("attack_id")
    techniques = techniques_for_family(family_id or "")
    genai_features = hints.get(
        "genai_features", _default_genai_features(family, entry_point)
    )

    payload: Dict[str, Any] = {
        "attack_family": family_id,
        "capability_ids": genai_caps,
        "channels": hints.get("channels", _default_channels(family)),
        "genai_features": genai_features,
        "family_signal_ids": list(family.get("observable_signal_ids") or []),
        "targeted_control_ids": list(family.get("targeted_control_ids") or []),
    }
    if techniques:
        technique = techniques[0]
        payload["technique"] = technique.action_type
        if technique.channel:
            payload["channel"] = technique.channel

    if action_type == "simulate_genai_context":
        payload.update({
            "agent_id": f"agent_{family_id or 'x'}".lower(),
            "agent_verified": hints.get("agent_verified", True),
            "mandate_scope": hints.get("mandate_scope", ["read", "purchase"]),
            "tool_scope": hints.get("tool_scope", ["search", "checkout"]),
            "requested_tools": hints.get("requested_tools", ["payment_api"]),
            "spend_limit": float(hints.get("spend_limit", 25000)),
            "requested_amount": float(hints.get("requested_amount", 40000)),
            "agent_mediated": True,
            "a2a_channel": family_id == "AG-004",
            "a2a_channel_authenticated": False,
            "counterparty_agent_unverified": family_id == "AG-002",
        })
    elif action_type == "simulate_social_engineering":
        payload.update({
            "channel": payload.get("channel", "voice"),
            "authentication_method": hints.get("authentication_method", "otp"),
            "victim_coerced": hints.get("victim_coerced", True),
            "recovery_flow": family_id == "AUTH-003",
        })
    elif action_type == "submit_kyc_evidence":
        payload.update({
            "evidence_type": hints.get(
                "evidence_type",
                "recovery_document" if family_id == "ATO-001" else "biometric",
            ),
        })
    elif action_type == "request_consent":
        broad = family_id == "OB-001"
        payload.update({
            "scopes": hints.get(
                "scopes",
                [
                    "accounts.read",
                    "accounts.write",
                    "payments.initiate",
                    "data.export_all",
                ] if broad else ["accounts.read"],
            ),
            "tpp_licensed": hints.get("tpp_licensed", family_id != "OB-002"),
            "tpp_registration_age_days": int(
                hints.get("tpp_registration_age_days", 5 if family_id == "OB-002" else 400)
            ),
            "tpp_risk_score": float(hints.get("tpp_risk_score", 0.7 if family_id == "OB-002" else 0.2)),
            "tpp_registration": family_id == "OB-002",
        })
    elif action_type == "establish_session":
        payload.update({
            "remote_access_active": family_id == "RAT-001",
            "accessibility_service_active": family_id == "RAT-001",
            "screen_overlay_active": family_id == "RAT-001",
            "headless_client": family_id == "BOT-001",
            "mean_interaction_interval_ms": float(
                hints.get("mean_interaction_interval_ms", 40 if family_id == "BOT-001" else 300)
            ),
            "behavioural_variance": float(
                hints.get("behavioural_variance", 0.04 if family_id == "BBE-001" else 0.4)
            ),
        })
    elif action_type == "orchestrate_network":
        ring_size = int(hints.get("ring_size", 5))
        payload.update({
            "member_customer_ids": hints.get(
                "member_customer_ids",
                [f"C_{(family_id or 'net').lower()}_{i}" for i in range(ring_size)],
            ),
            "shared_beneficiary_id": hints.get("shared_beneficiary_id", f"B_{(family_id or 'net').lower()}"),
            "aml_narrative_submitted": family_id == "AML-005",
        })

    return payload


def _default_channels(family: Dict[str, Any]) -> List[str]:
    attack_id = (family.get("attack_id") or "").upper()
    if attack_id.startswith("SEP"):
        return ["voice", "email"]
    if attack_id.startswith("AG"):
        return ["web", "agent"]
    if attack_id.startswith("ATO"):
        return ["video", "phone"]
    return ["web"]


def _default_genai_features(family: Dict[str, Any], entry_point: str) -> Dict[str, float]:
    attack_id = (family.get("attack_id") or "").upper()
    if entry_point == "social_engineering" or attack_id.startswith("SEP"):
        return {"social_engineering_score": 0.82, "vishing_risk": 0.70, "victim_coerced": 1.0}
    if attack_id.startswith("AG"):
        return {"prompt_injection_risk": 0.78, "agent_goal_anomaly": 0.72}
    if attack_id.startswith("ATO"):
        return {"document_forgery_score": 0.75, "recovery_fraud_risk": 0.68}
    return {"genai_anomaly_score": 0.55}


def build_plan_from_template(
    family: Dict[str, Any],
    stages: List[Dict],
    global_signals: List[Dict],
    hypothesis: Optional[Hypothesis] = None,
) -> AttackPlan:
    """Entry point used by kb_campaign_builder."""
    return KBTemplatePlanner().build_plan(family, stages, global_signals, hypothesis)
