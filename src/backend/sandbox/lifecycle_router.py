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
    "STG-0004": "authenticate",
    "STG-0005": "register_customer",
    "STG-0006": "open_account",
    "STG-0007": "link_beneficiary",
    "STG-0015": "onboard_merchant",
    "STG-0016": "onboard_merchant",
    "STG-0017": "onboard_merchant",
    "STG-0018": "onboard_merchant",
    "STG-0019": "verify_kyc",
    "STG-0020": "open_account",
    "STG-0028": "register_device",
}

ENTRY_POINTS = (
    "new_customer",
    "existing_customer",
    "merchant",
    "social_engineering",
    "genai_proxy",
    "cross_stage",
)


def derive_entry_point(family: Dict[str, Any]) -> str:
    """Derive campaign entry point from KB family metadata."""
    attack_id = (family.get("attack_id") or "").upper()
    template_id = family.get("simulation_template_id") or ""
    stage_id = family.get("lifecycle_stage_id") or ""
    cross = family.get("cross_stage_lifecycle_stage_ids") or []

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


def template_action_types(template: Optional[Dict[str, Any]], entry_point: str) -> List[str]:
    """Return supported_action_types from KB template, adjusted for entry point."""
    if not template:
        return proxy_template_actions(entry_point)

    actions = list(template.get("supported_action_types") or [])
    if not actions:
        return proxy_template_actions(entry_point)

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
    if entry_point == "social_engineering":
        return ["register_customer", "simulate_genai_context", "initiate_payment"]
    return ["simulate_genai_context", "register_customer", "initiate_payment"]


def setup_flags_for_entry(entry_point: str) -> Dict[str, Any]:
    """Default payload hints for register/payment steps by entry point."""
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
    return {"payment_path": "full"}
