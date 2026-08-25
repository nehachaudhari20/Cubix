"""Build the feature context consumed by the data-driven RuleEngine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .journey_correlation import build_journey_features


def build_rule_context(
    transaction: Dict[str, Any],
    state: Any,
    *,
    journey: Optional[List[Any]] = None,
    control_triggers: Optional[List[str]] = None,
    family: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Flatten transaction + sandbox state + journey into rule-evaluable fields."""
    customer_id = transaction.get("customer_id")
    beneficiary_id = transaction.get("beneficiary_id")
    customer = state.get_customer(customer_id) if state and customer_id else None
    beneficiary = (
        state.get_beneficiary(beneficiary_id) if state and beneficiary_id else None
    )

    amount = float(transaction.get("amount") or 0)
    genai = transaction.get("genai_context") or transaction.get("genai_features") or {}

    trust_score = float(getattr(customer, "trust_score", transaction.get("trust_score", 0.5)) or 0.5)
    verified = bool(getattr(customer, "verified", transaction.get("verified", True)))
    account_age_days = int(
        getattr(customer, "account_age_days", transaction.get("account_age_days", 0)) or 0
    )
    tx_count_24h = int(customer.get_tx_count_24h()) if customer else int(
        transaction.get("transaction_count_last_24h") or 0
    )
    tx_count_1h = int(customer.get_tx_count_1h()) if customer and hasattr(customer, "get_tx_count_1h") else int(
        transaction.get("transaction_count_last_1h") or 0
    )

    pan = (getattr(customer, "pan", "") or "").upper()
    synthetic_identity_flag = pan.startswith("SYN") or (len(set(pan)) <= 2 and len(pan) >= 4)

    is_new_beneficiary = bool(transaction.get("is_new_beneficiary"))
    if beneficiary and not is_new_beneficiary:
        is_new_beneficiary = bool(getattr(beneficiary, "is_new", False))

    shared_payers = 0
    if state and beneficiary_id and hasattr(state, "count_distinct_payers_to_beneficiary"):
        shared_payers = int(state.count_distinct_payers_to_beneficiary(beneficiary_id))

    now = datetime.now()
    hour = int(transaction.get("hour_of_day", now.hour))
    dow = int(transaction.get("day_of_week", now.weekday()))
    is_night = bool(transaction.get("is_night", hour < 6 or hour >= 22))

    family_signal_ids: List[str] = []
    expected_controls: List[str] = []
    if family:
        family_signal_ids = list(family.get("observable_signal_ids") or [])
        expected_controls = list(family.get("targeted_control_ids") or [])
    else:
        family_signal_ids = list(transaction.get("family_signal_ids") or transaction.get("observable_signal_ids") or [])
        expected_controls = list(
            transaction.get("expected_controls")
            or transaction.get("targeted_control_ids")
            or []
        )

    # Signal context active when GenAI path or multi-engine journey is in play
    signal_context_active = bool(
        genai
        or transaction.get("genai_proxy")
        or transaction.get("victim_coerced")
        or (journey and len(journey) >= 2)
        or family_signal_ids
    )

    journey_feats = build_journey_features(journey, control_triggers)

    ctx: Dict[str, Any] = {
        "amount": amount,
        "customer_id": customer_id,
        "device_id": transaction.get("device_id"),
        "beneficiary_id": beneficiary_id,
        "merchant_id": transaction.get("merchant_id"),
        "is_new_device": bool(transaction.get("is_new_device", False)),
        "is_unknown_device": bool(transaction.get("is_unknown_device", False)),
        "device_age_days": int(transaction.get("device_age_days") or 0),
        "is_new_beneficiary": is_new_beneficiary,
        "distinct_beneficiaries_last_24h": int(
            transaction.get("distinct_beneficiaries_last_24h") or 0
        ),
        "distinct_devices_last_7d": int(transaction.get("distinct_devices_last_7d") or 0),
        "transaction_count_last_24h": tx_count_24h,
        "transaction_count_last_1h": tx_count_1h,
        "velocity_score": float(transaction.get("velocity_score") or min(1.0, tx_count_24h / 10.0)),
        "trust_score": trust_score,
        "verified": verified,
        "account_age_days": account_age_days,
        "synthetic_identity_flag": synthetic_identity_flag,
        "merchant_risk_score": float(
            transaction.get("merchant_risk_score")
            or transaction.get("merchant_risk")
            or 0.3
        ),
        "merchant_familiarity_score": float(transaction.get("merchant_familiarity_score") or 0.5),
        "merchant_category_code": transaction.get("merchant_category_code") or transaction.get("mcc"),
        "payment_rail": (transaction.get("payment_rail") or "upi").lower(),
        "authentication_method": transaction.get("authentication_method") or "otp",
        "auth_success": transaction.get("auth_success", True),
        "hour_of_day": hour,
        "day_of_week": dow,
        "is_night": is_night,
        "round_amount_flag": amount > 0 and amount % 1000 == 0 and amount >= 10000,
        "shared_beneficiary_payers": shared_payers,
        "amount_to_avg_7d_ratio": float(transaction.get("amount_to_avg_7d_ratio") or 0),
        "amount_zscore_account": float(transaction.get("amount_zscore_account") or 0),
        "avg_amount_last_7d": float(
            customer.get_avg_amount_7d() if customer and hasattr(customer, "get_avg_amount_7d") else 0
        ),
        "account_tx_count_to_date": len(getattr(customer, "transactions", []) or []) if customer else 0,
        "family_signal_ids": family_signal_ids,
        "expected_controls": expected_controls,
        "targeted_control_ids": expected_controls,
        "signal_context_active": signal_context_active,
        "attack_family": transaction.get("attack_family") or transaction.get("family_id"),
        "genai_load_bearing_flag": bool(
            genai.get("genai_load_bearing_flag")
            or transaction.get("genai_load_bearing")
        ),
        "genai_amplified_flag": bool(genai.get("genai_amplified_flag")),
        **{k: v for k, v in genai.items() if isinstance(v, (int, float, bool))},
        **journey_feats,
    }
    return ctx
