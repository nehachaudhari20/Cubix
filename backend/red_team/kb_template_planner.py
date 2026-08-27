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
    "simulate_genai_context": "Simulate GenAI attack context",
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
        elif action_type == "simulate_genai_context":
            base.update({
                "attack_family": family.get("attack_id"),
                "capability_ids": genai_caps,
                "channels": hints.get("channels", _default_channels(family)),
                "genai_features": hints.get("genai_features", _default_genai_features(family, entry_point)),
                "victim_coerced": hints.get("victim_coerced", entry_point == "social_engineering"),
                "agent_mediated": entry_point in ("genai_proxy", "cross_stage"),
            })

        return base


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
