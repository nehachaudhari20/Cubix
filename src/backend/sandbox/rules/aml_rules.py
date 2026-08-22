"""AML / Compliance risk rules."""

from datetime import datetime, timedelta
from typing import Any, Dict

from .base import BaseRule


class AMLRules(BaseRule):
    """Anti-money laundering and structuring detection rules."""

    def __init__(self):
        super().__init__("AML / Compliance")

    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        customer = features.get("customer")
        amount = features.get("amount", 0)
        risk_contribution = 0.0
        triggered_rules = []

        if not customer:
            return {
                "rule_set": "aml_rules",
                "risk_contribution": 0.0,
                "triggered_rules": [],
                "kb_controls_active": self.kb_controls_list(),
            }

        struct_min = self.get_control_value("structuring_min_amount", 20000)
        struct_max = self.get_control_value("structuring_max_amount", 24999)
        struct_count_threshold = int(self.get_control_value("structuring_count_threshold", 3))
        high_amount_threshold = self.get_control_value("high_amount_aml_threshold", 50000)

        cutoff = datetime.now() - timedelta(hours=24)
        recent = [
            t for t in customer.transactions
            if (ts := t.get("timestamp")) is not None and ts > cutoff
        ]

        structuring_count = sum(
            1 for t in recent
            if struct_min <= t.get("amount", 0) <= struct_max
        )
        if structuring_count >= struct_count_threshold:
            risk = self.get_control_value("structuring_risk", 0.35)
            risk_contribution += risk
            triggered_rules.append(f"structuring_{structuring_count}_tx_in_band")

        if amount >= high_amount_threshold and customer.trust_score < 0.5:
            risk = self.get_control_value("high_amount_aml_risk", 0.25)
            risk_contribution += risk
            triggered_rules.append("high_amount_low_trust")

        if amount > 0 and amount % 10000 == 0:
            risk = self.get_control_value("round_amount_risk", 0.10)
            risk_contribution += risk
            triggered_rules.append("round_amount_pattern")

        if self.has_kb_control("structuring", "transaction_monitoring", "velocity"):
            if structuring_count >= 2 and not any(t.startswith("structuring_") for t in triggered_rules):
                risk_contribution += 0.10
                triggered_rules.append("kb_aml_monitoring_escalation")

        return {
            "rule_set": "aml_rules",
            "risk_contribution": min(0.5, risk_contribution),
            "triggered_rules": triggered_rules,
            "structuring_count_24h": structuring_count,
            "thresholds_applied": {
                "structuring_band": [struct_min, struct_max],
                "structuring_count_threshold": struct_count_threshold,
            },
            "kb_controls_active": self.kb_controls_list(),
        }
