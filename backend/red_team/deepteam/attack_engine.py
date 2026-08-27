"""Transform -> Vary -> Validate attack engine (DeepTeam AttackEngine analogue)."""

from __future__ import annotations

import os
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional

from backend.llm import get_llm, invoke_text, use_llm_enabled
from backend.sandbox.rules.compiled_controls import CompiledControlSet
from backend.sandbox.rules.control_compiler import ControlCompiler

from .schemas import MutationPayload, ValidatedVariation, VariationSet

PAYMENT_RAILS = ("upi", "card", "bank_transfer", "wallet", "imps", "neft")

GENAI_FEATURE_PROFILES: Dict[str, Dict[str, float]] = {
    "prompt_injection": {"prompt_injection_risk": 0.85, "agent_goal_anomaly": 0.72},
    "social_engineering": {"social_engineering_score": 0.82, "vishing_risk": 0.70, "victim_coerced": 1.0},
    "doc_forgery": {"document_forgery_score": 0.78, "recovery_fraud_risk": 0.65},
    "anomaly_spike": {"genai_anomaly_score": 0.88, "agent_goal_anomaly": 0.80},
}


def _strict_llm_validation() -> bool:
    return os.environ.get("RED_TEAM_ATTACK_ENGINE_STRICT_LLM", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def _max_variations() -> int:
    try:
        return max(3, min(40, int(os.environ.get("RED_TEAM_ENGINE_MAX_VARIATIONS", "20"))))
    except ValueError:
        return 20


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
        tier1 = float(
            ControlCompiler.get_threshold_for_parameter(
                self.compiled, "PAR-AMOUNT", "amount_limit_tier1", 25000
            )
        )
        tier2 = float(
            ControlCompiler.get_threshold_for_parameter(
                self.compiled, "PAR-AMOUNT", "amount_limit_tier2", 50000
            )
        )
        base_amount = float(base.get("amount") or tier1)
        variations: List[ValidatedVariation] = []
        limit = _max_variations()

        def add(label: str, payload: Dict[str, Any]) -> None:
            if len(variations) >= limit:
                return
            variations.append(
                ValidatedVariation(
                    variation_id=f"var_{uuid.uuid4().hex[:8]}",
                    label=label,
                    action_payload=payload,
                    validation_status="PENDING",
                )
            )

        # --- Amount ladder (risk-score movers) ---
        for label, amount in (
            ("amount_just_below_tier1", round(tier1 * 0.95, 2)),
            ("amount_just_above_tier1", round(tier1 * 1.05, 2)),
            ("amount_2x_base", round(base_amount * 2, 2)),
            ("amount_half_base", round(max(100.0, base_amount * 0.5), 2)),
            ("amount_tier2_probe", round(tier2 * 0.98, 2)),
            ("amount_tier2_breach", round(tier2 * 1.1, 2)),
            ("amount_micro_probe", 2500.0),
            ("amount_structuring", 9500.0),
        ):
            v = deepcopy(base)
            v["amount"] = amount
            add(label, v)

        # --- Timing ---
        for hour, label in ((2, "timing_2am"), (14, "timing_afternoon"), (23, "timing_late")):
            v = deepcopy(base)
            v["hour"] = hour
            add(label, v)

        # --- Beneficiary ---
        v = deepcopy(base)
        v["beneficiary_id"] = mutation.beneficiary_id or f"BEN_SYN_{uuid.uuid4().hex[:6]}"
        add("new_beneficiary", v)

        # --- Payment rails ---
        current_rail = str(base.get("payment_rail") or "upi").lower()
        for rail in PAYMENT_RAILS:
            if rail == current_rail:
                continue
            v = deepcopy(base)
            v["payment_rail"] = rail
            add(f"rail_{rail}", v)

        # --- GenAI feature profiles (risk movers for GenAI engine) ---
        for name, feats in GENAI_FEATURE_PROFILES.items():
            v = deepcopy(base)
            existing = dict(v.get("genai_features") or {})
            existing.update(feats)
            v["genai_features"] = existing
            if feats.get("victim_coerced"):
                v["victim_coerced"] = True
            add(f"genai_{name}", v)

        # --- Combined high-risk: night + high amount + alt rail ---
        v = deepcopy(base)
        v["amount"] = round(max(base_amount, tier1) * 1.5, 2)
        v["hour"] = 2
        v["payment_rail"] = "wallet" if current_rail != "wallet" else "upi"
        add("combo_night_high_alt_rail", v)

        return variations[:limit]

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
