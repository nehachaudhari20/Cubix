"""
Lifecycle Engine Registry — maps all 49 KB stages to sandbox engines.

The payment cycle spans many lifecycle stages; this registry ensures each STG-*
has a dedicated engine rather than collapsing everything into one payment chain.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

# KB stage_id → sandbox engine key
STAGE_TO_ENGINE: Dict[str, str] = {
    "STG-0001": "agent_commerce",   # GenAI / AI-Agent Commerce
    "STG-0002": "payment_init",
    "STG-0003": "gateway",
    "STG-0004": "auth",
    "STG-0005": "kyc",
    "STG-0006": "account",
    "STG-0007": "beneficiary",
    "STG-0008": "authz",
    "STG-0009": "aml",
    "STG-0010": "mule",
    "STG-0011": "settlement",
    "STG-0012": "investigation",
    "STG-0013": "insider",
    "STG-0014": "reporting",
    "STG-0015": "acquirer",
    "STG-0016": "acquirer",
    "STG-0017": "acquirer",
    "STG-0018": "acquirer",
    "STG-0019": "kyc",
    "STG-0020": "account",
    "STG-0021": "beneficiary",
    "STG-0022": "payment_init",
    "STG-0023": "gateway",
    "STG-0024": "auth",
    "STG-0025": "authz",
    "STG-0026": "aml",
    "STG-0027": "settlement",
    "STG-0028": "device",
    "STG-0029": "risk",
    "STG-0030": "mule",
    "STG-0031": "agent_commerce",
    "STG-0032": "gateway",
    "STG-0033": "acquirer",
    "STG-0034": "aml",
    "STG-0035": "investigation",
    "STG-0036": "reporting",
    "STG-0037": "insider",
    "STG-0038": "beneficiary",
    "STG-0039": "payment_init",
    "STG-0040": "risk",
    "STG-0041": "auth",
    "STG-0042": "kyc",
    "STG-0043": "device",
    "STG-0044": "settlement",
    "STG-0045": "acquirer",
    "STG-0046": "gateway",
    "STG-0047": "aml",
    "STG-0048": "mule",
    "STG-0049": "agent_commerce",
}

# Human-readable engine catalog (15 distinct engines covering 49 stages)
ENGINE_CATALOG: Dict[str, str] = {
    "agent_commerce": "GenAI / AI-Agent Commerce (STG-0001, STG-0031, STG-0049)",
    "kyc": "Identity / KYC (STG-0005, STG-0019, STG-0042)",
    "device": "Device Trust (STG-0028, STG-0043)",
    "auth": "Authentication (STG-0004, STG-0024, STG-0041)",
    "account": "Account Creation (STG-0006, STG-0020)",
    "beneficiary": "Beneficiary (STG-0007, STG-0021, STG-0038)",
    "payment_init": "Payment Initiation (STG-0002, STG-0022, STG-0039)",
    "gateway": "Gateway / Processor (STG-0003, STG-0023, STG-0032, STG-0046)",
    "aml": "AML / Compliance (STG-0009, STG-0026, STG-0034, STG-0047)",
    "risk": "Risk Scoring (STG-0029, STG-0040)",
    "authz": "Authorization (STG-0008, STG-0025)",
    "settlement": "Settlement (STG-0011, STG-0027, STG-0044)",
    "acquirer": "Acquirer / Merchant (STG-0015..0018, STG-0033, STG-0045)",
    "mule": "Mule / Cash-out (STG-0010, STG-0030, STG-0048)",
    "investigation": "Investigation (STG-0012, STG-0035)",
    "insider": "Insider (STG-0013, STG-0037)",
    "reporting": "Reporting (STG-0014, STG-0036)",
}

# Payment path profiles — expanded to include lifecycle stage engines
PAYMENT_PATHS: Dict[str, List[str]] = {
    "full": [
        "kyc", "device", "auth", "beneficiary", "payment_init", "gateway",
        "aml", "mule", "risk", "authz", "settlement",
    ],
    "existing_customer": [
        "device", "auth", "beneficiary", "payment_init", "gateway",
        "aml", "risk", "authz", "settlement",
    ],
    "auth_risk": [
        "auth", "beneficiary", "payment_init", "gateway", "aml", "risk", "authz", "settlement",
    ],
    "risk_only": [
        "payment_init", "gateway", "aml", "risk", "authz", "settlement",
    ],
    "merchant_focus": [
        "payment_init", "gateway", "acquirer", "aml", "risk", "authz", "settlement",
    ],
    "genai_victim_payment": [
        "beneficiary", "payment_init", "gateway", "aml", "mule", "risk", "authz", "settlement",
    ],
    "cross_stage_full": [
        "agent_commerce", "kyc", "device", "auth", "beneficiary", "payment_init",
        "gateway", "aml", "mule", "risk", "authz", "settlement",
    ],
}

JOURNEY_STEP_NAMES: Dict[str, str] = {
    "agent_commerce": "AI-Agent Commerce",
    "kyc": "KYC",
    "device": "Device",
    "auth": "Authentication",
    "account": "Account",
    "beneficiary": "Beneficiary",
    "payment_init": "Payment Initiation",
    "gateway": "Gateway/Processor",
    "aml": "AML/Compliance",
    "mule": "Mule/Cash-out",
    "risk": "Risk",
    "authz": "Authorization",
    "settlement": "Settlement",
    "acquirer": "Acquirer",
}


def engines_for_stages(stage_ids: List[str]) -> List[str]:
    """Resolve ordered unique engine keys for a list of KB stage IDs."""
    ordered: List[str] = []
    seen: Set[str] = set()
    for stage_id in stage_ids:
        engine = STAGE_TO_ENGINE.get(stage_id)
        if engine and engine not in seen and engine not in ("investigation", "insider", "reporting", "account", "risk"):
            ordered.append(engine)
            seen.add(engine)
    return ordered


def engines_for_family_stages(stage_records: List[dict]) -> List[str]:
    ids = [s.get("stage_id") for s in stage_records if s.get("stage_id")]
    return engines_for_stages(ids)


def payment_path_engines(path: str, family_stage_engines: Optional[List[str]] = None) -> List[str]:
    """Merge payment path profile with optional family-specific stage engines."""
    base = list(PAYMENT_PATHS.get(path, PAYMENT_PATHS["full"]))
    if not family_stage_engines:
        return base
    merged: List[str] = []
    seen: Set[str] = set()
    for key in family_stage_engines + base:
        if key not in seen:
            merged.append(key)
            seen.add(key)
    return merged
