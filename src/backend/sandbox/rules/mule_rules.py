"""Cash-out / Mule detection rules."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .base import BaseRule
from .compiled_controls import CompiledControlSet


class MuleRules(BaseRule):
    """Detect mule-like beneficiary and pass-through patterns."""

    def __init__(self, compiled_controls: Optional[CompiledControlSet] = None):
        super().__init__("Cash-out / Mule", compiled_controls=compiled_controls)

    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        beneficiary = features.get("beneficiary")
        amount = features.get("amount", 0)
        state = features.get("state")
        beneficiary_id = features.get("beneficiary_id")
        risk_contribution = 0.0
        triggered_rules = []

        new_beneficiary_hours = int(self.get_control_value("new_beneficiary_hours", 24))
        new_beneficiary_amount = self.get_control_value("new_beneficiary_amount_threshold", 25000)
        shared_threshold = int(self.get_control_value("shared_beneficiary_customers_threshold", 3))

        if beneficiary:
            age_hours = (datetime.now() - beneficiary.created_at).total_seconds() / 3600
            if age_hours <= new_beneficiary_hours and amount >= new_beneficiary_amount:
                risk = self.get_control_value("new_beneficiary_risk", 0.35)
                risk_contribution += risk
                triggered_rules.append("new_beneficiary_high_amount")

            ben_risk_threshold = self.get_control_value("high_beneficiary_risk_threshold", 0.60)
            if beneficiary.risk_score >= ben_risk_threshold:
                risk = self.get_control_value("high_beneficiary_risk_contribution", 0.25)
                risk_contribution += risk
                triggered_rules.append("high_risk_beneficiary")

            if not beneficiary.is_verified:
                risk_contribution += 0.15
                triggered_rules.append("unverified_beneficiary")

        if state and beneficiary_id:
            payer_count = state.count_distinct_payers_to_beneficiary(beneficiary_id)
            if payer_count >= shared_threshold:
                risk = self.get_control_value("shared_beneficiary_risk", 0.40)
                risk_contribution += risk
                triggered_rules.append(f"shared_beneficiary_{payer_count}_payers")

        if self.has_kb_control("mule", "pass-through", "layering"):
            if amount >= 20000 and beneficiary and not triggered_rules:
                risk_contribution += 0.10
                triggered_rules.append("kb_mule_pattern_watch")

        return {
            "rule_set": "mule_rules",
            "risk_contribution": min(0.5, risk_contribution),
            "triggered_rules": triggered_rules,
            "thresholds_applied": {
                "new_beneficiary_hours": new_beneficiary_hours,
                "new_beneficiary_amount": new_beneficiary_amount,
            },
            "kb_controls_active": self.kb_controls_list(),
        }
