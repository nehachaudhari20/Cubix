"""
Executable control registry — numeric thresholds mapped to KB lifecycle stages.

KB stores control *names* (strings); this registry provides executable *values*
used by sandbox rules. When USE_KB_API=true, KB control names are merged as
enabled flags but numeric thresholds come from here unless overridden later.
"""

from typing import Any, Dict, List, Optional

# Registry keys -> executable control values
EXECUTABLE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "identity_kyc": {
        "low_trust_threshold": 0.35,
        "young_account_days": 30,
        "low_trust_risk": 0.25,
        "unverified_identity_risk": 0.35,
        "young_account_risk": 0.15,
        "synthetic_identity_risk": 0.30,
    },
    "aml_compliance": {
        "structuring_min_amount": 20000,
        "structuring_max_amount": 24999,
        "structuring_count_threshold": 3,
        "structuring_risk": 0.35,
        "high_amount_aml_threshold": 50000,
        "high_amount_aml_risk": 0.25,
        "round_amount_risk": 0.10,
    },
    "mule_cashout": {
        "new_beneficiary_hours": 24,
        "new_beneficiary_amount_threshold": 25000,
        "new_beneficiary_risk": 0.35,
        "high_beneficiary_risk_threshold": 0.60,
        "high_beneficiary_risk_contribution": 0.25,
        "shared_beneficiary_customers_threshold": 3,
        "shared_beneficiary_risk": 0.40,
    },
    "payment_initiation": {
        "amount_limit_tier1": 25000,
        "amount_limit_tier2": 50000,
        "amount_limit_tier3": 100000,
        "amount_tier1_risk": 0.25,
        "amount_tier2_risk": 0.25,
        "amount_tier3_risk": 0.25,
        "velocity_limit_24h": 5,
        "velocity_high_risk": 10,
        "velocity_tier1_risk": 0.25,
        "velocity_tier2_risk": 0.50,
    },
    "device_session": {
        "new_device_risk": 0.20,
        "device_age_threshold": 30,
        "device_age_risk": 0.10,
        "unknown_device_risk": 0.30,
    },
    "merchant": {
        "merchant_high_risk_threshold": 0.70,
        "merchant_very_high_risk_threshold": 0.90,
        "merchant_high_risk_contribution": 0.25,
        "merchant_very_high_risk_contribution": 0.25,
    },
    "authorization": {
        "allow_threshold": 0.30,
        "challenge_threshold": 0.60,
        "velocity_limit_24h": 5,
    },
}

# KB stage names (and aliases) -> registry key
STAGE_ALIASES: Dict[str, str] = {
    "identity/kyc": "identity_kyc",
    "identity_kyc": "identity_kyc",
    "identity / kyc (stage 1)": "identity_kyc",
    "aml / compliance": "aml_compliance",
    "aml_compliance": "aml_compliance",
    "cash-out / mule": "mule_cashout",
    "cash-out/mule (conversion/cash-out)": "mule_cashout",
    "cash-out/mule (movement/layering)": "mule_cashout",
    "cash-out/mule (recruitment)": "mule_cashout",
    "payment initiation": "payment_initiation",
    "payment_initiation": "payment_initiation",
    "device/session (stage 3)": "device_session",
    "device / session (stage 3)": "device_session",
    "device_session": "device_session",
    "merchant (stage 6)": "merchant",
    "merchant": "merchant",
    "authorization": "authorization",
    "authorization (stage 10)": "authorization",
}


def resolve_registry_key(stage: str) -> Optional[str]:
    """Map a stage name to a registry key."""
    normalized = stage.strip().lower().replace("_", " ")
    normalized = " ".join(normalized.split())

    if normalized in STAGE_ALIASES:
        return STAGE_ALIASES[normalized]

    # Partial match (e.g. "Device / Session (Stage 3)" contains "device")
    for alias, key in STAGE_ALIASES.items():
        if alias in normalized or normalized in alias:
            return key

    return None


def get_registry_defaults(stage: str) -> Dict[str, Any]:
    """Return executable defaults for a lifecycle stage."""
    key = resolve_registry_key(stage)
    if key and key in EXECUTABLE_DEFAULTS:
        return dict(EXECUTABLE_DEFAULTS[key])
    return {}


def merge_kb_control_names(defaults: Dict[str, Any], kb_controls: List[Any]) -> Dict[str, Any]:
    """Merge KB string control names as enabled flags alongside numeric defaults."""
    merged = dict(defaults)
    enabled: List[str] = []

    for control in kb_controls:
        if isinstance(control, str):
            key = control.lower().replace(" ", "_").replace("/", "_")
            enabled.append(key)
            merged[f"kb_enabled__{key}"] = True
        elif isinstance(control, dict):
            name = control.get("control_name") or control.get("name")
            if name:
                key = name.lower().replace(" ", "_")
                enabled.append(key)
                value = control.get("value")
                if isinstance(value, (int, float)):
                    merged[key] = value
                else:
                    merged[f"kb_enabled__{key}"] = True

    merged["_kb_control_names"] = enabled
    return merged
