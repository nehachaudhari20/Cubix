"""
Attack Generator Agent — builds executable sandbox sequences.

Payment steps optionally expand through PaymentAttackEngine into ALL valid
variations (rails, amounts, GenAI features, timing) for sandbox execution.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..schemas import AttackPlan, ActionPayload, GeneratedSequence, PlanStep
from ..agent_helpers import new_campaign_ids
from ..utils import BaselineLoader
from ..deepteam.attack_engine import PaymentAttackEngine
from ..deepteam.mutation_builder import (
    merge_variation_into_payment,
    mutation_from_plan_step,
)
from ..deepteam.strategy_config import use_attack_engine
from backend.sandbox.rules.compiled_controls import CompiledControlSet, get_global_compiled_controls
from backend.sandbox.rules.control_compiler import ControlCompiler


def _execute_all_variations() -> bool:
    return os.environ.get("RED_TEAM_ENGINE_EXECUTE_ALL", "true").lower() in ("1", "true", "yes")


def _engine_payment_mode() -> str:
    """final | all — which payment steps receive attack-engine expansion.

    Default is ``final`` when executing all variations (avoids N_payments × 20 explosion).
    Set RED_TEAM_ENGINE_PAYMENTS_ONLY=all to expand every payment step.
    """
    explicit = os.environ.get("RED_TEAM_ENGINE_PAYMENTS_ONLY")
    if explicit is not None and explicit.strip() != "":
        return explicit.strip().lower()
    return "final" if _execute_all_variations() else "all"


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

        for idx, step in enumerate(plan.steps):
            expanded = self._expand_step(step, ids, idx, plan)
            payloads.extend(expanded)

        # Renumber for stable step indices after variation expansion
        total = len(payloads)
        renumbered: List[ActionPayload] = []
        for i, p in enumerate(payloads):
            renumbered.append(
                p.model_copy(
                    update={
                        "step": i + 1,
                        "total_steps": total,
                        "is_final": i == total - 1,
                    }
                )
            )

        return GeneratedSequence(
            campaign_id=ids["campaign_id"],
            payloads=renumbered,
            total_payloads=len(renumbered),
        )

    def _expand_step(
        self,
        step: PlanStep,
        ids: Dict[str, str],
        idx: int,
        plan: AttackPlan,
    ) -> List[ActionPayload]:
        action_payload, meta = self._build_action_payload(step, ids, idx, plan)

        # Non-payment or no engine expansion → single payload
        if step.action_type != "initiate_payment" or not meta.get("engine_variations"):
            return [
                ActionPayload(
                    action_type=step.action_type,
                    action_payload=action_payload,
                    step=step.step,
                    total_steps=len(plan.steps),
                    is_final=False,
                    campaign_id=ids["campaign_id"],
                    attack_family=plan.primary_family,
                    attack_variant=plan.selected_variant,
                    target_control=step.target_control,
                    expected_outcome=step.expected_outcome,
                    narrative=self._build_narrative(step, plan, action_payload, meta),
                    variation_label=meta.get("variation_label"),
                    engine_validated=bool(meta.get("engine_validated")),
                )
            ]

        variations: List[Tuple[str, Dict[str, Any]]] = meta["engine_variations"]
        out: List[ActionPayload] = []
        for label, var_payload in variations:
            var_meta = {"variation_label": label, "engine_validated": True}
            out.append(
                ActionPayload(
                    action_type=step.action_type,
                    action_payload=var_payload,
                    step=step.step,
                    total_steps=len(plan.steps),
                    is_final=False,
                    campaign_id=ids["campaign_id"],
                    attack_family=plan.primary_family,
                    attack_variant=plan.selected_variant,
                    target_control=step.target_control,
                    expected_outcome=step.expected_outcome,
                    narrative=self._build_narrative(step, plan, var_payload, var_meta),
                    variation_label=label,
                    engine_validated=True,
                )
            )
        return out

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
        mode = _engine_payment_mode()
        if mode in ("all", "every", "true", "1"):
            return True
        payment_steps = [s for s in plan.steps if s.action_type == "initiate_payment"]
        return bool(payment_steps and step.step == payment_steps[-1].step)

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
            "amount": payment.get("amount", self.baseline.sample_amount()),
            "payment_rail": payment.get("payment_rail", self.baseline.sample_rail()),
            "authentication_method": payment.get("authentication_method", "otp"),
            "merchant_risk_score": payment.get("merchant_risk_score", 0.3),
            "beneficiary_id": payment.get("beneficiary_id"),
            "merchant_id": payment.get("merchant_id"),
            "account_id": payment.get("account_id"),
            "genai_features": payment.get("genai_features") or {},
            "capability_ids": payment.get("capability_ids") or [],
            "attack_family": payment.get("attack_family"),
        }
        result = self.attack_engine.generate(mutation, legitimate)
        valid = [
            v for v in result.variations
            if getattr(v, "validation_status", "VALID") == "VALID"
        ]
        if not valid:
            return payment, meta

        if _execute_all_variations():
            # Include base payment + every valid variation for sandbox execution
            engine_variations: List[Tuple[str, Dict[str, Any]]] = [
                ("base_payment", dict(payment)),
            ]
            for v in valid:
                merged = merge_variation_into_payment(payment, v.action_payload)
                merged["transaction_id"] = f"txn_{uuid.uuid4().hex[:8]}"
                engine_variations.append((v.label, merged))
            meta["engine_variations"] = engine_variations
            meta["engine_validated"] = True
            meta["variation_label"] = f"expanded_{len(engine_variations)}"
            return payment, meta

        # Legacy: pick one
        from ..deepteam.mutation_builder import pick_variation_for_step
        picked = pick_variation_for_step(valid, step)
        if not picked:
            return payment, meta
        label = next(
            (v.label for v in valid if v.action_payload == picked),
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
                f"INR {action_payload.get('amount', 0)} rail={action_payload.get('payment_rail')} "
                f"targeting {step.target_control}{engine_note}"
            )
        return f"Step {step.step}: {step.action} ({step.action_type}){engine_note}"
