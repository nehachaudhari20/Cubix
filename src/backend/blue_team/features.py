"""
FeatureBuilder — maps Sandbox transaction + state to FraudShield feature vector.

Uses the same feature names as train_model.py CANDIDATE_FEATURES so training
and inference stay aligned.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

# Mirror train_model.py — subset used at inference with sandbox-available fields
SANDBOX_FEATURES = [
    "amount",
    "payment_rail",
    "transaction_type",
    "authentication_method",
    "card_present",
    "auth_success",
    "currency",
    "merchant_category_code",
    "merchant_risk_score",
    "merchant_familiarity_score",
    "device_age_days",
    "account_age_days",
    "is_new_device",
    "is_new_beneficiary",
    "velocity_score",
    "transaction_count_last_1h",
    "transaction_count_last_24h",
    "avg_amount_last_1d",
    "avg_amount_last_7d",
    "amount_to_avg_7d_ratio",
    "amount_zscore_account",
    "seconds_since_prev_tx",
    "distinct_beneficiaries_last_24h",
    "distinct_devices_last_7d",
    "account_tx_count_to_date",
    "campaign_step",
    "hour_of_day",
    "day_of_week",
    "is_night",
]


class FeatureBuilder:
    """Build a feature dict from a sandbox transaction and SandboxState."""

    def build(
        self,
        transaction: Dict[str, Any],
        state: Any,
    ) -> Dict[str, Any]:
        customer_id = transaction.get("customer_id")
        device_id = transaction.get("device_id")
        beneficiary_id = transaction.get("beneficiary_id")
        amount = float(transaction.get("amount") or 0)

        customer = state.get_customer(customer_id) if customer_id and state else None
        device = state.get_device(device_id) if device_id and state else None
        merchant_id = transaction.get("merchant_id")
        merchant = state.get_merchant(merchant_id) if merchant_id and state else None
        beneficiary = (
            state.get_beneficiary(beneficiary_id) if beneficiary_id and state else None
        )

        now = datetime.now()
        tx_count_24h = customer.get_tx_count_24h() if customer else 0
        avg_7d = customer.get_avg_amount_7d() if customer else 0.0
        account_age = getattr(customer, "account_age_days", 0) if customer else 0
        if customer and account_age == 0 and hasattr(customer, "created_at"):
            account_age = max(0, (now - customer.created_at).days)

        device_age = transaction.get("device_age_days", 0)
        if device and device_age == 0:
            device_age = device.get_age_days()

        prev_tx_seconds = 86400.0
        if customer and customer.transactions:
            last = customer.transactions[-1]
            last_ts = last.get("timestamp")
            if last_ts and isinstance(last_ts, datetime):
                prev_tx_seconds = max(1.0, (now - last_ts).total_seconds())

        amount_to_avg = amount / avg_7d if avg_7d > 0 else 1.0
        amount_zscore = 0.0
        if customer and customer.transactions:
            amounts = [t.get("amount", 0) for t in customer.transactions[-20:]]
            if len(amounts) > 1:
                std = float(np.std(amounts)) or 1.0
                amount_zscore = (amount - float(np.mean(amounts))) / std

        velocity_score = min(1.0, tx_count_24h / 10.0)

        if state:
            from .graph.graph_signals import GraphSignalBuilder

            graph_signals = GraphSignalBuilder(state, reference_time=now).build(
                transaction, include_graph_extras=True
            )
        else:
            graph_signals = {}

        row = {
            "amount": amount,
            "payment_rail": transaction.get("payment_rail", "upi"),
            "transaction_type": transaction.get("transaction_type", "transfer"),
            "authentication_method": transaction.get("authentication_method", "otp"),
            "card_present": int(transaction.get("card_present", 0)),
            "auth_success": int(transaction.get("auth_success", 1)),
            "currency": transaction.get("currency", "INR"),
            "merchant_category_code": (
                merchant.mcc if merchant else transaction.get("merchant_mcc", "5411")
            ),
            "merchant_risk_score": float(
                transaction.get("merchant_risk_score", merchant.risk_score if merchant else 0.3)
            ),
            "merchant_familiarity_score": float(transaction.get("merchant_familiarity_score", 0.5)),
            "device_age_days": int(device_age),
            "account_age_days": int(account_age),
            "is_new_device": int(transaction.get("is_new_device", True)),
            "is_new_beneficiary": int(
                transaction.get("is_new_beneficiary", beneficiary is not None)
            ),
            "velocity_score": round(velocity_score, 4),
            "transaction_count_last_1h": min(tx_count_24h, 20),
            "transaction_count_last_24h": tx_count_24h,
            "avg_amount_last_1d": avg_7d,
            "avg_amount_last_7d": avg_7d,
            "amount_to_avg_7d_ratio": round(amount_to_avg, 4),
            "amount_zscore_account": round(amount_zscore, 4),
            "seconds_since_prev_tx": prev_tx_seconds,
            "distinct_beneficiaries_last_24h": 0,
            "distinct_devices_last_7d": 0,
            "account_tx_count_to_date": len(customer.transactions) if customer else 0,
            "campaign_step": int(transaction.get("campaign_step", 1)),
            "hour_of_day": now.hour,
            "day_of_week": now.weekday(),
            "is_night": int(now.hour < 6 or now.hour >= 22),
        }
        row.update(graph_signals)
        if not graph_signals:
            row["distinct_beneficiaries_last_24h"] = 1 if beneficiary_id else 0
            row["distinct_devices_last_7d"] = 1 if device_id else 0

        genai = transaction.get("genai_features") or transaction.get("genai_context") or {}
        if genai:
            for key, val in genai.items():
                if key not in row:
                    row[key] = val

        return row

    def to_model_vector(
        self,
        row: Dict[str, Any],
        feature_order: List[str],
        categorical_features: List[str],
        categorical_mappings: Dict[str, Dict[str, int]],
        unseen_code: int = -1,
    ) -> List[float]:
        """Encode a feature row into a model input vector."""
        vector = []
        for col in feature_order:
            val = row.get(col)
            if col in categorical_features:
                mapping = categorical_mappings.get(col, {})
                encoded = mapping.get(str(val) if val is not None else "NA", unseen_code)
                vector.append(float(encoded))
            else:
                try:
                    vector.append(float(val) if val is not None and val == val else 0.0)
                except (TypeError, ValueError):
                    vector.append(0.0)
        return vector
