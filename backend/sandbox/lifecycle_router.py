"""
Lifecycle router — maps KB stages, entry points, and payment paths to sandbox engines.

Not every attack runs KYC → Device → Auth → Payment. The orchestrator uses this
module to decide which engines participate per action.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# Payment execution profiles — 15 engines covering 49 KB lifecycle stages
from .lifecycle_engine_registry import PAYMENT_PATHS, STAGE_TO_ENGINE, ENGINE_CATALOG  # noqa: E402

# KB lifecycle stage_id → primary sandbox action (when composing cross-stage campaigns)
STAGE_ID_TO_ACTION: Dict[str, str] = {
    "STG-0001": "simulate_genai_context",
    "STG-0002": "initiate_payment",
    "STG-0003": "simulate_genai_context",
    "STG-0004": "simulate_social_engineering",
    "STG-0005": "register_customer",
    "STG-0006": "open_account",
    "STG-0007": "link_beneficiary",
    "STG-0009": "orchestrate_network",
    "STG-0015": "onboard_merchant",
    "STG-0016": "onboard_merchant",
    "STG-0017": "onboard_merchant",
    "STG-0018": "onboard_merchant",
    "STG-0019": "submit_kyc_evidence",
    "STG-0020": "open_account",
    "STG-0028": "establish_session",
    "STG-0039": "submit_kyc_evidence",
    "STG-0042": "request_consent",
    "STG-0043": "request_consent",
    "STG-0048": "orchestrate_network",
}

# Surface → the template that drives it (kept in sync with scripts/enable_surface_families.py)
SURFACE_TEMPLATE_IDS: Dict[str, str] = {
    "agent": "TPL-AGENT",
    "auth_se": "TPL-AUTH-SE",
    "kyc": "TPL-KYC-GENAI",
    "open_banking": "TPL-OB-CONSENT",
    "device": "TPL-SESSION",
    "network": "TPL-NETWORK",
}

# Entry point per non-payment surface — drives payload defaults and, for surfaces
# with a cash-out leg, the payment path of the final step.
SURFACE_ENTRY_POINTS: Dict[str, str] = {
    "agent": "agent_surface",
    "auth_se": "auth_se_surface",
    "kyc": "kyc_surface",
    "open_banking": "consent_surface",
    "device": "device_surface",
    "network": "network_surface",
}

ENTRY_POINTS = (
    "new_customer",
    "existing_customer",
    "merchant",
    "social_engineering",
    "genai_proxy",
    "cross_stage",
    "agent_surface",
    "auth_se_surface",
    "kyc_surface",
    "consent_surface",
    "device_surface",
    "network_surface",
)


def derive_entry_point(family: Dict[str, Any]) -> str:
    """Derive campaign entry point from KB family metadata."""
    attack_id = (family.get("attack_id") or "").upper()
    template_id = family.get("simulation_template_id") or ""
    stage_id = family.get("lifecycle_stage_id") or ""
    cross = family.get("cross_stage_lifecycle_stage_ids") or []

    # A family carrying a surface is adjudicated by that surface's control chain,
    # not by being forced through a payment leg.
    surface = family.get("surface")
    if surface and surface in SURFACE_ENTRY_POINTS:
        return SURFACE_ENTRY_POINTS[surface]

    if family.get("sandbox_executable") is False:
        if attack_id.startswith("SEP") or "social" in (family.get("name") or "").lower():
            return "social_engineering"
        return "genai_proxy"

    if len(cross) >= 2:
        return "cross_stage"

    if template_id == "TPL-MERCHANT" or stage_id.startswith("STG-0015"):
        return "merchant"
    if template_id == "TPL-AUTH" or attack_id.startswith("ATO"):
        return "existing_customer"
    if stage_id == "STG-0001":
        return "genai_proxy"
    return "new_customer"


def payment_path_for_entry(entry_point: str, payload: Optional[Dict[str, Any]] = None) -> str:
    """Resolve payment path from entry point and optional payload override."""
    if payload and payload.get("payment_path"):
        path = str(payload["payment_path"])
        if path in PAYMENT_PATHS:
            return path
    mapping = {
        "new_customer": "full",
        "existing_customer": "existing_customer",
        "merchant": "merchant_focus",
        "social_engineering": "genai_victim_payment",
        "genai_proxy": "risk_only",
        "cross_stage": "cross_stage_full",
        # Non-payment surfaces only reach a payment path on a cash-out leg.
        "agent_surface": "risk_only",
        "auth_se_surface": "genai_victim_payment",
        "kyc_surface": "full",
        "consent_surface": "risk_only",
        "device_surface": "existing_customer",
        "network_surface": "cross_stage_full",
    }
    return mapping.get(entry_point, "full")


def resolve_payment_path(payload: Dict[str, Any], entry_point: Optional[str] = None) -> str:
    ep = entry_point or payload.get("entry_point") or "new_customer"
    return payment_path_for_entry(ep, payload)


def stages_to_action_types(family: Dict[str, Any], stage_records: List[Dict[str, Any]]) -> List[str]:
    """Build ordered sandbox actions from KB primary + cross-stage lifecycle stages."""
    ordered: List[str] = []
    seen: Set[str] = set()

    for stage in stage_records:
        stage_id = stage.get("stage_id") or ""
        action = STAGE_ID_TO_ACTION.get(stage_id)
        if not action or action in seen:
            continue
        # Gateway/processor is enforced inside payment_init — skip duplicate payment steps
        if action == "initiate_payment" and "initiate_payment" in seen:
            continue
        ordered.append(action)
        seen.add(action)

    entry = derive_entry_point(family)
    if entry == "genai_proxy" and "simulate_genai_context" not in seen:
        ordered.insert(0, "simulate_genai_context")
    if entry == "social_engineering":
        if "register_customer" not in seen:
            ordered.insert(0, "register_customer")
        if "simulate_genai_context" not in seen:
            ordered.append("simulate_genai_context")

    if family.get("sandbox_executable") and "initiate_payment" not in seen:
        ordered.append("initiate_payment")

    return ordered


SURFACE_ENTRY_TO_SURFACE = {v: k for k, v in SURFACE_ENTRY_POINTS.items()}


def template_action_types(template: Optional[Dict[str, Any]], entry_point: str) -> List[str]:
    """Return supported_action_types from KB template, adjusted for entry point."""
    if not template:
        return proxy_template_actions(entry_point)

    actions = list(template.get("supported_action_types") or [])
    if not actions:
        return proxy_template_actions(entry_point)

    # Surface templates already list the exact sequence for their control chain.
    if entry_point in SURFACE_ENTRY_TO_SURFACE:
        return actions

    if entry_point == "existing_customer":
        if "authenticate" not in actions:
            actions.insert(0, "authenticate")
    elif entry_point == "merchant":
        actions = [a for a in actions if a not in ("register_customer", "register_device")]
        if "onboard_merchant" not in actions:
            actions.insert(0, "onboard_merchant")
    elif entry_point in ("genai_proxy", "social_engineering"):
        return proxy_template_actions(entry_point)

    return actions


def proxy_template_actions(entry_point: str) -> List[str]:
    surface = SURFACE_ENTRY_TO_SURFACE.get(entry_point)
    if surface:
        from backend.taxonomy import SURFACE_ENTRY_ACTION

        return ["register_customer", SURFACE_ENTRY_ACTION[surface]]
    if entry_point == "social_engineering":
        return ["register_customer", "simulate_social_engineering", "initiate_payment"]
    return ["simulate_genai_context", "register_customer", "initiate_payment"]


def setup_flags_for_entry(entry_point: str) -> Dict[str, Any]:
    """Default payload hints for register/surface/payment steps by entry point."""
    if entry_point == "existing_customer":
        return {
            "trust_score": 0.88,
            "verified": True,
            "account_age_days": 730,
            "payment_path": "existing_customer",
        }
    if entry_point == "merchant":
        return {"payment_path": "merchant_focus", "skip_payer_setup": True}
    if entry_point == "social_engineering":
        return {
            "trust_score": 0.82,
            "verified": True,
            "account_age_days": 900,
            "payment_path": "genai_victim_payment",
            "victim_coerced": True,
        }
    if entry_point == "genai_proxy":
        return {"payment_path": "risk_only", "genai_proxy": True}
    if entry_point == "cross_stage":
        return {"payment_path": "cross_stage_full"}

    # --- non-payment surfaces ---
    if entry_point == "agent_surface":
        return {
            "trust_score": 0.75,
            "verified": True,
            "account_age_days": 365,
            "payment_path": "risk_only",
            "agent_mediated": True,
        }
    if entry_point == "auth_se_surface":
        return {
            "trust_score": 0.80,
            "verified": True,
            "account_age_days": 720,
            "payment_path": "genai_victim_payment",
            "victim_coerced": True,
        }
    if entry_point == "kyc_surface":
        # Onboarding: no history, identity being established right now.
        return {
            "trust_score": 0.30,
            "verified": False,
            "account_age_days": 0,
            "payment_path": "full",
        }
    if entry_point == "consent_surface":
        return {
            "trust_score": 0.78,
            "verified": True,
            "account_age_days": 540,
            "payment_path": "risk_only",
        }
    if entry_point == "device_surface":
        return {
            "trust_score": 0.82,
            "verified": True,
            "account_age_days": 900,
            "payment_path": "existing_customer",
        }
    if entry_point == "network_surface":
        return {
            "trust_score": 0.55,
            "verified": True,
            "account_age_days": 90,
            "payment_path": "cross_stage_full",
        }
    return {"payment_path": "full"}
