"""Identity / KYC risk rules."""

from typing import Any, Dict

from .base import BaseRule


class IdentityRules(BaseRule):
    """Rules based on customer identity and KYC trust signals."""

    def __init__(self):
        super().__init__("Identity/KYC")

    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        customer = features.get("customer")
        risk_contribution = 0.0
        triggered_rules = []

        if not customer:
            return {
                "rule_set": "identity_rules",
                "risk_contribution": 0.0,
                "triggered_rules": ["no_customer_data"],
                "kb_controls_active": self.kb_controls_list(),
            }

        low_trust_threshold = self.get_control_value("low_trust_threshold", 0.35)
        young_account_days = self.get_control_value("young_account_days", 30)

        if customer.trust_score < low_trust_threshold:
            risk = self.get_control_value("low_trust_risk", 0.25)
            risk_contribution += risk
            triggered_rules.append("low_trust_score")

        if not customer.verified:
            risk = self.get_control_value("unverified_identity_risk", 0.35)
            risk_contribution += risk
            triggered_rules.append("unverified_identity")

        if customer.account_age_days < young_account_days and customer.trust_score < 0.7:
            risk = self.get_control_value("young_account_risk", 0.15)
            risk_contribution += risk
            triggered_rules.append(f"account_younger_than_{young_account_days}_days")

        pan = (customer.pan or "").upper()
        if pan.startswith("SYN") or (len(set(pan)) <= 2 and len(pan) >= 4):
            risk = self.get_control_value("synthetic_identity_risk", 0.30)
            risk_contribution += risk
            triggered_rules.append("synthetic_identity_pattern")

        if self.has_kb_control("synthetic", "identity", "document"):
            if "synthetic_identity_pattern" not in triggered_rules and customer.trust_score < 0.5:
                risk_contribution += 0.10
                triggered_rules.append("kb_synthetic_identity_detection")

        return {
            "rule_set": "identity_rules",
            "risk_contribution": min(0.5, risk_contribution),
            "triggered_rules": triggered_rules,
            "thresholds_applied": {
                "low_trust_threshold": low_trust_threshold,
                "young_account_days": young_account_days,
            },
            "kb_controls_active": self.kb_controls_list(),
        }
