"""
Actor-scoped state snapshots for the Sandbox journey viewer.

The Sandbox holds the whole synthetic world in memory. The UI only needs the
entities a given action actually touched, captured immediately before and
after execution so the timeline can show what the action changed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _customer_view(customer: Any) -> Dict[str, Any]:
    return {
        "customer_id": customer.customer_id,
        "name": customer.name,
        "verified": customer.verified,
        "trust_score": round(float(customer.trust_score), 3),
        "account_age_days": customer.account_age_days,
        "created_at": _iso(customer.created_at),
        "tx_count_total": len(customer.transactions),
        "tx_count_24h": customer.get_tx_count_24h(),
        "avg_amount_7d": round(customer.get_avg_amount_7d(), 2),
    }


def _device_view(device: Any) -> Dict[str, Any]:
    return {
        "device_id": device.device_id,
        "customer_id": device.customer_id,
        "is_known": device.is_known,
        "age_days": device.get_age_days(),
        "first_seen": _iso(device.first_seen),
        "last_seen": _iso(device.last_seen),
        "fingerprint": device.fingerprint,
    }


def _merchant_view(merchant: Any) -> Dict[str, Any]:
    return {
        "merchant_id": merchant.merchant_id,
        "name": merchant.name,
        "mcc": merchant.mcc,
        "declared_mcc": merchant.declared_mcc,
        "mcc_mismatch": merchant.mcc != merchant.declared_mcc,
        "risk_score": round(float(merchant.risk_score), 3),
        "kyb_verified": merchant.kyb_verified,
        "created_at": _iso(merchant.created_at),
    }


def _beneficiary_view(beneficiary: Any) -> Dict[str, Any]:
    return {
        "beneficiary_id": beneficiary.beneficiary_id,
        "customer_id": beneficiary.customer_id,
        "name": beneficiary.name,
        "account_ref": beneficiary.account_ref,
        "is_verified": beneficiary.is_verified,
        "risk_score": round(float(beneficiary.risk_score), 3),
        "created_at": _iso(beneficiary.created_at),
    }


def snapshot_state(sandbox: Any, action_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Capture the entities referenced by one action payload."""
    if sandbox is None or not hasattr(sandbox, "get_state"):
        return {}

    state = sandbox.get_state()
    snapshot: Dict[str, Any] = {
        "world": {
            "customers": len(state.customers),
            "devices": len(state.devices),
            "merchants": len(state.merchants),
            "beneficiaries": len(state.beneficiaries),
            "accounts": len(state.accounts),
            "transactions_logged": len(state.transaction_log),
        }
    }

    lookups = (
        ("customer", "customer_id", state.get_customer, _customer_view),
        ("device", "device_id", state.get_device, _device_view),
        ("merchant", "merchant_id", state.get_merchant, _merchant_view),
        ("beneficiary", "beneficiary_id", state.get_beneficiary, _beneficiary_view),
    )

    for key, field, getter, view in lookups:
        entity_id: Optional[str] = action_payload.get(field)
        if not entity_id:
            continue
        entity = getter(entity_id)
        snapshot[key] = view(entity) if entity else {"id": entity_id, "exists": False}

    return snapshot


def diff_snapshots(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the leaf values that changed between two snapshots."""
    changes: Dict[str, Any] = {}
    for section, after_values in after.items():
        before_values = before.get(section)
        if not isinstance(after_values, dict) or not isinstance(before_values, dict):
            continue
        for field, new_value in after_values.items():
            old_value = before_values.get(field)
            if old_value != new_value:
                changes[f"{section}.{field}"] = {"before": old_value, "after": new_value}
    return changes
