"""Maps sandbox rule trigger strings to canonical KB control IDs (CTL-*)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

# (trigger_prefix_or_exact, control_id, rule_set)
TRIGGER_IMPLEMENTATIONS: List[Tuple[str, str, str]] = [
    ("amount_exceeds_", "CTL-0105", "amount_rules"),
    ("velocity_exceeds_", "CTL-0013", "velocity_rules"),
    ("new_beneficiary_high_amount", "CTL-0009", "mule_rules"),
    ("high_risk_beneficiary", "CTL-0009", "mule_rules"),
    ("unverified_beneficiary", "CTL-0009", "mule_rules"),
    ("shared_beneficiary_", "CTL-0009", "mule_rules"),
    ("kb_mule_pattern_watch", "CTL-0009", "mule_rules"),
    ("unknown_device", "CTL-0096", "device_rules"),
    ("new_device_less_than_7_days", "CTL-0096", "device_rules"),
    ("device_age_less_than_", "CTL-0096", "device_rules"),
    ("low_trust_score", "CTL-0172", "identity_rules"),
    ("unverified_identity", "CTL-0018", "identity_rules"),
    ("account_younger_than_", "CTL-0268", "identity_rules"),
    ("synthetic_identity_pattern", "CTL-0018", "identity_rules"),
    ("kb_synthetic_identity_detection", "CTL-0018", "identity_rules"),
    ("structuring_", "CTL-0276", "aml_rules"),
    ("high_amount_low_trust", "CTL-0276", "aml_rules"),
    ("round_amount_pattern", "CTL-0276", "aml_rules"),
    ("kb_aml_monitoring_escalation", "CTL-0324", "aml_rules"),
    ("merchant_very_high_risk", "CTL-0323", "merchant_rules"),
    ("merchant_high_risk", "CTL-0323", "merchant_rules"),
    ("velocity_exceeded", "CTL-0013", "authorization"),
    ("composite_new_device_low_trust_high_amount", "CTL-0096", "composite"),
    ("composite_beneficiary_velocity_structuring", "CTL-0009", "composite"),
    ("composite_gateway_merchant_risk", "CTL-0323", "composite"),
    ("composite_genai_payment", "CTL-0236", "composite"),
    ("composite_journey_multi_engine_flags", "CTL-0140", "composite"),
    ("composite_young_account_mule", "CTL-0009", "composite"),
    ("signal_", "CTL-0140", "signal_rules"),
]

REGISTRY_KEY_CONTROLS: Dict[str, str] = {
    "payment_initiation.amount_limit_tier1": "CTL-0105",
    "payment_initiation.amount_limit_tier2": "CTL-0105",
    "payment_initiation.amount_limit_tier3": "CTL-0105",
    "payment_initiation.velocity_limit_24h": "CTL-0013",
    "payment_initiation.velocity_high_risk": "CTL-0013",
    "mule_cashout.new_beneficiary_amount_threshold": "CTL-0009",
    "device_session.device_age_threshold": "CTL-0096",
    "identity_kyc.low_trust_threshold": "CTL-0172",
    "identity_kyc.young_account_days": "CTL-0268",
    "authorization.allow_threshold": "CTL-0140",
    "authorization.challenge_threshold": "CTL-0140",
}


def build_trigger_map(kb_path: str = "data/knowledge/canonical") -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for prefix, control_id, _rule_set in TRIGGER_IMPLEMENTATIONS:
        mapping[prefix] = control_id

    rules_path = Path(kb_path) / "defense" / "rules.json"
    if not rules_path.exists():
        rules_path = Path(kb_path) / "rules.json"
    if rules_path.exists():
        try:
            rules = json.loads(rules_path.read_text(encoding="utf-8")).get("rules") or []
            for rule in rules:
                trigger = rule.get("trigger")
                control_id = rule.get("control_id")
                if trigger and control_id:
                    mapping[trigger] = control_id
        except Exception:
            pass
    return mapping
