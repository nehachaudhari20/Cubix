"""
Attack Generator Agent — builds executable sandbox action sequences.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List

from ..schemas import AttackPlan, ActionPayload, GeneratedSequence
from ..agent_helpers import new_campaign_ids
from ..utils import BaselineLoader


class AttackGenerator:
    """Generates concrete sandbox actions from attack plans."""

    def __init__(self, model_name: str = None):
        self.baseline = BaselineLoader()

    def generate_sequence(self, plan: AttackPlan) -> GeneratedSequence:
        ids = new_campaign_ids(plan.campaign_name.replace(" ", "_").lower()[:8])
        payloads: List[ActionPayload] = []
        num_steps = len(plan.steps)

        for idx, step in enumerate(plan.steps):
            action_payload = self._build_action_payload(step, ids, idx, plan)
            narrative = self._build_narrative(step, plan, action_payload)

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
            ))

        return GeneratedSequence(
            campaign_id=ids["campaign_id"],
            payloads=payloads,
            total_payloads=len(payloads),
        )

    def _build_action_payload(self, step, ids: Dict[str, str], idx: int, plan: AttackPlan) -> Dict[str, Any]:
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
            }

        if action_type == "register_device":
            return {
                "device_id": ids["device_id"],
                "customer_id": ids["customer_id"],
                "fingerprint": tpl.get("fingerprint", {"browser": "Chrome", "os": "Windows"}),
            }

        if action_type == "open_account":
            return {
                "account_id": ids["account_id"],
                "customer_id": ids["customer_id"],
                "balance": float(tpl.get("balance", 75000)),
            }

        if action_type == "onboard_merchant":
            return {
                "merchant_id": ids["merchant_id"],
                "name": tpl.get("name", f"Merchant {ids['merchant_id']}"),
                "mcc": str(tpl.get("mcc", "5411")),
                "declared_mcc": str(tpl.get("declared_mcc", tpl.get("mcc", "5411"))),
                "kyb_verified": tpl.get("kyb_verified", True),
                "risk_score": float(tpl.get("risk_score", 0.3)),
                "owner_customer_id": ids["customer_id"],
            }

        if action_type == "link_beneficiary":
            return {
                "beneficiary_id": ids["beneficiary_id"],
                "customer_id": ids["customer_id"],
                "name": tpl.get("name", "External Payee"),
                "account_ref": tpl.get("account_ref", f"EXT-{ids['beneficiary_id']}"),
                "risk_score": float(tpl.get("risk_score", 0.25)),
            }

        # initiate_payment
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
            "location_country": tpl.get("location_country", self.baseline.sample_country()),
            "location_region": tpl.get("location_region", self.baseline.sample_region()),
        }

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

        return payment

    def _build_narrative(self, step, plan: AttackPlan, action_payload: Dict[str, Any]) -> str:
        if step.action_type == "initiate_payment":
            return (
                f"Step {step.step}/{len(plan.steps)}: {plan.primary_family} payment of "
                f"₹{action_payload.get('amount', 0)} targeting {step.target_control}"
            )
        return f"Step {step.step}: {step.action} ({step.action_type})"
