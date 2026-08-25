"""Build MutationPayload from plan steps and compiled control thresholds."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.red_team.schemas import PlanStep
from backend.sandbox.rules.compiled_controls import CompiledControlSet
from backend.sandbox.rules.control_compiler import ControlCompiler

from .schemas import MutationPayload


def mutation_from_plan_step(
    step: PlanStep,
    compiled: Optional[CompiledControlSet] = None,
) -> MutationPayload:
    tpl = dict(step.payload_template or {})
    compiled = compiled or ControlCompiler().compile()

    amount = tpl.get("amount")
    if amount is None and step.action_type == "initiate_payment":
        amount = ControlCompiler.get_threshold_for_parameter(
            compiled, "PAR-AMOUNT", "amount_limit_tier1", 25000
        )

    extra = {
        key: value
        for key, value in tpl.items()
        if key not in {"amount", "hour", "beneficiary_id", "device_id", "payment_rail", "trust_score"}
    }
    return MutationPayload(
        amount=float(amount) if amount is not None else None,
        hour=tpl.get("hour"),
        beneficiary_id=tpl.get("beneficiary_id"),
        device_id=tpl.get("device_id"),
        payment_rail=tpl.get("payment_rail"),
        trust_score=tpl.get("trust_score"),
        extra=extra,
    )


def merge_variation_into_payment(base: Dict[str, Any], variation: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay attack-engine variation onto a fully-built sandbox payment payload."""
    merged = dict(base)
    for key, value in variation.items():
        if value is not None:
            merged[key] = value
    return merged


def pick_variation_for_step(
    variations: list,
    step: PlanStep,
) -> Optional[Dict[str, Any]]:
    """Choose the best validated variation for a plan step."""
    if not variations:
        return None
    target_amount = (step.payload_template or {}).get("amount")
    if target_amount is not None:
        for item in variations:
            payload = item.action_payload if hasattr(item, "action_payload") else item
            if abs(float(payload.get("amount", 0)) - float(target_amount)) < 1:
                return payload
    first = variations[0]
    return first.action_payload if hasattr(first, "action_payload") else first
