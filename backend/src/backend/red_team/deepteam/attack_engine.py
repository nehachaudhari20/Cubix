"""Transform -> Vary -> Validate attack engine (DeepTeam AttackEngine analogue). Phase 2."""

from __future__ import annotations

import os
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional

from backend.llm import get_llm, invoke_text, use_llm_enabled
from backend.sandbox.rules.compiled_controls import CompiledControlSet
from backend.sandbox.rules.control_compiler import ControlCompiler

from .schemas import MutationPayload, ValidatedVariation, VariationSet


def _strict_llm_validation() -> bool:
    return os.environ.get("RED_TEAM_ATTACK_ENGINE_STRICT_LLM", "false").lower() in (
        "1",
        "true",
        "yes",
    )


class PaymentAttackEngine:
    """Generate validated payment payload variations from baseline + mutation."""

    def __init__(self, compiled_controls: Optional[CompiledControlSet] = None):
        self.compiled = compiled_controls or ControlCompiler().compile()

    def generate(
        self,
        raw_mutation: MutationPayload | Dict[str, Any],
        legitimate_payment: Dict[str, Any],
    ) -> VariationSet:
        mutation = (
            raw_mutation
            if isinstance(raw_mutation, MutationPayload)
            else MutationPayload.model_validate(raw_mutation)
        )
        base = self._transform(legitimate_payment, mutation)
        candidates = self._vary(base, mutation)
        results: List[ValidatedVariation] = []
        valid_count = 0

        for item in candidates:
            ok, reason = self._validate(item.action_payload)
            item.validation_status = "VALID" if ok else "INVALID"
            item.validation_reason = reason
            results.append(item)
            if ok:
                valid_count += 1

        return VariationSet(
            source_mutation=mutation,
            variations=results,
            valid_count=valid_count,
            attempted_count=len(results),
        )

    def _transform(self, legitimate: Dict[str, Any], mutation: MutationPayload) -> Dict[str, Any]:
        merged = deepcopy(legitimate)
        if mutation.amount is not None:
            merged["amount"] = mutation.amount
        if mutation.hour is not None:
            merged["hour"] = mutation.hour
        if mutation.beneficiary_id:
            merged["beneficiary_id"] = mutation.beneficiary_id
        if mutation.device_id:
            merged["device_id"] = mutation.device_id
        if mutation.payment_rail:
            merged["payment_rail"] = mutation.payment_rail
        if mutation.trust_score is not None:
            merged["trust_score"] = mutation.trust_score
        merged.update(mutation.extra)
        return merged

    def _vary(self, base: Dict[str, Any], mutation: MutationPayload) -> List[ValidatedVariation]:
        tier1 = ControlCompiler.get_threshold_for_parameter(
            self.compiled, "PAR-AMOUNT", "amount_limit_tier1", 25000
        )
        variations: List[ValidatedVariation] = []

        amount_2x = round(float(base.get("amount", tier1)) * 2 if base.get("amount") else float(tier1) * 2, 2)
        v1 = deepcopy(base)
        v1["amount"] = amount_2x
        variations.append(ValidatedVariation(
            variation_id=f"var_{uuid.uuid4().hex[:8]}",
            label="amount_2x_threshold",
            action_payload=v1,
            validation_status="PENDING",
        ))

        v2 = deepcopy(base)
        v2["hour"] = 2
        variations.append(ValidatedVariation(
            variation_id=f"var_{uuid.uuid4().hex[:8]}",
            label="timing_2am",
            action_payload=v2,
            validation_status="PENDING",
        ))

        v3 = deepcopy(base)
        v3["beneficiary_id"] = mutation.beneficiary_id or f"BEN_SYN_{uuid.uuid4().hex[:6]}"
        variations.append(ValidatedVariation(
            variation_id=f"var_{uuid.uuid4().hex[:8]}",
            label="new_beneficiary",
            action_payload=v3,
            validation_status="PENDING",
        ))
        return variations

    def _is_structurally_valid(self, payload: Dict[str, Any]) -> bool:
        if not payload:
            return False
        if "amount" not in payload and "beneficiary_id" not in payload:
            return False
        if "amount" in payload:
            try:
                float(payload["amount"])
            except (TypeError, ValueError):
                return False
        return True

    def _validate(self, payload: Dict[str, Any]) -> tuple[bool, str]:
        if not self._is_structurally_valid(payload):
            return False, "missing amount or beneficiary_id"

        llm = get_llm()
        if llm is None or not use_llm_enabled():
            return True, "structural check only (LLM disabled)"

        if not _strict_llm_validation():
            return True, "red-team permissive mode (set RED_TEAM_ATTACK_ENGINE_STRICT_LLM=true to filter)"

        system = (
            "You evaluate SYNTHETIC payment payloads for authorized red-team sandbox simulation. "
            "Adversarial patterns are expected. Return VALID if structurally complete, INVALID if malformed."
        )
        user = (
            "Does this JSON have the required fields for a sandbox payment test "
            "(amount, identifiers)? Return VALID or INVALID only.\n\n"
            f"{payload}"
        )
        text = (invoke_text(llm, system, user) or "").strip().upper()
        if "VALID" in text and "INVALID" not in text:
            return True, "LLM approved"
        return False, f"LLM rejected: {text[:80]}"
