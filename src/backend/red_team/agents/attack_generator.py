"""
Attack Generator Agent — builds executable sandbox sequences.

Payment steps optionally pass through PaymentAttackEngine (Transform -> Vary -> Validate).
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from ..schemas import AttackPlan, ActionPayload, GeneratedSequence, PlanStep
from ..agent_helpers import new_campaign_ids
from ..utils import BaselineLoader
from ..deepteam.attack_engine import PaymentAttackEngine
from ..deepteam.mutation_builder import (
    merge_variation_into_payment,
    mutation_from_plan_step,
    pick_variation_for_step,
)
from ..deepteam.strategy_config import use_attack_engine
from backend.sandbox.rules.compiled_controls import CompiledControlSet, get_global_compiled_controls
from backend.sandbox.rules.control_compiler import ControlCompiler


class AttackGenerator:
    """Generates concrete sandbox actions from attack plans."""

    def __init__(
        self,
        model_name: str = None,
        compiled_controls: Optional[CompiledControlSet] = None,
    ):
        self.baseline = BaselineLoader()
        self.compiled = compiled_controls or get_global_compiled_controls() or ControlCompiler().compile()
        self.use_engine = use_attack_engine()
        self.attack_engine = PaymentAttackEngine(self.compiled) if self.use_engine else None

    def generate_sequence(self, plan: AttackPlan) -> GeneratedSequence:
        ids = new_campaign_ids(plan.campaign_name.replace(" ", "_").lower()[:8])
        payloads: List[ActionPayload] = []
        num_steps = len(plan.steps)

        for idx, step in enumerate(plan.steps):
            action_payload, meta = self._build_action_payload(step, ids, idx, plan)
            narrative = self._build_narrative(step, plan, action_payload, meta)

            payloads.append(ActionPayload(
                action_type=step.action_type,
                action_payload=action_payload,
                step=step.step,
                total_steps=num_steps,
                is_final=idx == num_steps - 1,
                campaign_id=ids["campaign_id"],
                attack_family=plan.primary_family,
                attack_variant=plan.selected_variant,
                target_control=step.target_control,
                expected_outcome=step.expected_outcome,
                narrative=narrative,
                variation_label=meta.get("variation_label"),
                engine_validated=bool(meta.get("engine_validated")),
            ))

        return GeneratedSequence(
            campaign_id=ids["campaign_id"],
            payloads=payloads,
            total_payloads=len(payloads),
        )

    def _build_action_payload(
        self,
        step: PlanStep,
        ids: Dict[str, str],
        idx: int,
        plan: AttackPlan,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        meta: Dict[str, Any] = {"engine_validated": False}
        tpl = dict(step.payload_template or {})
        action_type = step.action_type

        if action_type == "register_customer":
            return {
                "customer_id": ids["customer_id"],
                "name": tpl.get("name", f"Customer {ids['customer_id']}"),
                "pan": tpl.get("pan", "SYN0000001"),
                "dob": tpl.get("dob", "1990-01-01"),
                "address": tpl.get("address", "Synthetic City"),
                "trust_score": float(tpl.get("trust_score", 0.65)),
                "verified": tpl.get("verified", True),
            }, meta

        if action_type == "register_device":
            return {
                "device_id": ids["device_id"],
                "customer_id": ids["customer_id"],
                "fingerprint": tpl.get("fingerprint", {"browser": "Chrome", "os": "Windows"}),
            }, meta

        if action_type == "authenticate":
            return {
                "customer_id": ids["customer_id"],
                "authentication_method": tpl.get("authentication_method", "otp"),
            }, meta

        if action_type == "open_account":
            return {
                "account_id": ids["account_id"],
                "customer_id": ids["customer_id"],
                "balance": float(tpl.get("balance", 75000)),
            }, meta

        if action_type == "onboard_merchant":
            payload = {
                "merchant_id": ids["merchant_id"],
                "name": tpl.get("name", f"Merchant {ids['merchant_id']}"),
                "mcc": str(tpl.get("mcc", "5411")),
                "declared_mcc": str(tpl.get("declared_mcc", tpl.get("mcc", "5411"))),
                "kyb_verified": tpl.get("kyb_verified", True),
                "risk_score": float(tpl.get("risk_score", 0.3)),
            }
            if not tpl.get("skip_payer_setup"):
                payload["owner_customer_id"] = ids["customer_id"]
            return payload, meta

        if action_type == "link_beneficiary":
            return {
                "beneficiary_id": ids["beneficiary_id"],
                "customer_id": ids["customer_id"],
                "name": tpl.get("name", "External Payee"),
                "account_ref": tpl.get("account_ref", f"EXT-{ids['beneficiary_id']}"),
                "risk_score": float(tpl.get("risk_score", 0.25)),
            }, meta

        if action_type == "simulate_genai_context":
            return {
                "attack_family": plan.primary_family,
                "customer_id": ids.get("customer_id"),
                "capability_ids": tpl.get("capability_ids") or [],
                "channels": tpl.get("channels") or [],
                "genai_features": tpl.get("genai_features") or {},
                "victim_coerced": tpl.get("victim_coerced", False),
                "agent_mediated": tpl.get("agent_mediated", False),
            }, meta

        payment = self._build_payment_payload(step, ids, idx, plan, tpl)
        if self.attack_engine and self._should_apply_engine(step, plan):
            payment, meta = self._apply_attack_engine(payment, step)
        return payment, meta

    def _build_payment_payload(
        self,
        step: PlanStep,
        ids: Dict[str, str],
        idx: int,
        plan: AttackPlan,
        tpl: Dict[str, Any],
    ) -> Dict[str, Any]:
        amount = tpl.get("amount")
        if amount is None:
            base = self.baseline.sample_amount()
            amount = base * (1 + idx * 0.8)

        payment = {
            "transaction_id": f"txn_{uuid.uuid4().hex[:8]}",
            "customer_id": ids["customer_id"],
            "device_id": ids["device_id"],
            "amount": round(float(amount), 2),
            "payment_rail": tpl.get("payment_rail", self.baseline.sample_rail()),
            "authentication_method": tpl.get("authentication_method", "otp"),
            "merchant_risk_score": float(tpl.get("merchant_risk_score", self.baseline.sample_merchant_risk())),
        }

        if tpl.get("hour") is not None:
            payment["hour"] = tpl["hour"]

        if any(s.action_type == "onboard_merchant" for s in plan.steps):
            payment["merchant_id"] = ids.get("merchant_id")
        elif tpl.get("merchant_id"):
            payment["merchant_id"] = tpl["merchant_id"]

        if any(s.action_type == "link_beneficiary" for s in plan.steps):
            payment["beneficiary_id"] = ids.get("beneficiary_id")
        elif tpl.get("beneficiary_id"):
            payment["beneficiary_id"] = tpl["beneficiary_id"]

        if any(s.action_type == "open_account" for s in plan.steps):
            payment["account_id"] = tpl.get("account_id", ids.get("account_id"))

        payment["payment_path"] = tpl.get("payment_path")
        payment["entry_point"] = tpl.get("entry_point") or getattr(plan, "entry_point", None)
        genai_feats = dict(tpl.get("genai_features") or {})
        for prior in plan.steps:
            if prior.step >= step.step:
                break
            if prior.action_type == "simulate_genai_context":
                pt = prior.payload_template or {}
                genai_feats.update(pt.get("genai_features") or {})
                if pt.get("victim_coerced"):
                    payment["victim_coerced"] = True
                if pt.get("capability_ids"):
                    payment.setdefault("capability_ids", pt["capability_ids"])
        if genai_feats:
            payment["genai_features"] = genai_feats
        if tpl.get("capability_ids"):
            payment["capability_ids"] = tpl["capability_ids"]
        if tpl.get("victim_coerced"):
            payment["victim_coerced"] = tpl["victim_coerced"]
        payment["attack_family"] = plan.primary_family

        return payment

    def _should_apply_engine(self, step: PlanStep, plan: AttackPlan) -> bool:
        if step.action_type != "initiate_payment":
            return False
        if os.environ.get("RED_TEAM_ENGINE_PAYMENTS_ONLY", "final").lower() == "final":
            payment_steps = [s for s in plan.steps if s.action_type == "initiate_payment"]
            return payment_steps and step.step == payment_steps[-1].step
        return True

    def _apply_attack_engine(
        self,
        payment: Dict[str, Any],
        step: PlanStep,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        meta: Dict[str, Any] = {"engine_validated": False}
        mutation = mutation_from_plan_step(step, self.compiled)
        mutation.beneficiary_id = mutation.beneficiary_id or payment.get("beneficiary_id")
        legitimate = {
            "customer_id": payment.get("customer_id"),
            "device_id": payment.get("device_id"),
            "amount": self.baseline.sample_amount(),
            "payment_rail": payment.get("payment_rail", self.baseline.sample_rail()),
            "authentication_method": payment.get("authentication_method", "otp"),
            "merchant_risk_score": payment.get("merchant_risk_score", 0.3),
        }
        result = self.attack_engine.generate(mutation, legitimate)
        if not result.variations:
            return payment, meta
        picked = pick_variation_for_step(result.variations, step)
        if not picked:
            return payment, meta
        label = next(
            (v.label for v in result.variations if v.action_payload == picked),
            "engine_variation",
        )
        meta["variation_label"] = label
        meta["engine_validated"] = True
        return merge_variation_into_payment(payment, picked), meta

    def _build_narrative(
        self,
        step: PlanStep,
        plan: AttackPlan,
        action_payload: Dict[str, Any],
        meta: Dict[str, Any],
    ) -> str:
        engine_note = f" [{meta['variation_label']}]" if meta.get("variation_label") else ""
        if step.action_type == "initiate_payment":
            return (
                f"Step {step.step}/{len(plan.steps)}: {plan.primary_family} payment of "
                f"INR {action_payload.get('amount', 0)} targeting {step.target_control}{engine_note}"
            )
        return f"Step {step.step}: {step.action} ({step.action_type}){engine_note}"
