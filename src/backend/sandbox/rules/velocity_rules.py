"""Velocity-Based Static Rules with KB API Integration"""

from typing import Dict, Any
from .base import BaseRule


class VelocityRules(BaseRule):
    """Rules based on transaction velocity."""
    
    def __init__(self):
        super().__init__("Payment Initiation")
    
    def _get_default_controls(self) -> Dict[str, Any]:
        return {
            "velocity_limit_24h": 5,
            "velocity_high_risk": 10,
            "velocity_low_risk": 3,
            "velocity_tier1_risk": 0.25,
            "velocity_tier2_risk": 0.50
        }
    
    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate velocity-based rules using KB controls."""
        risk_contribution = 0.0
        triggered_rules = []
        
        customer = features.get("customer")
        if not customer:
            return {
                "rule_set": "velocity_rules",
                "risk_contribution": 0.0,
                "triggered_rules": ["no_customer_data"],
                "tx_count_24h": 0
            }
        
        # Fetch controls from KB API
        limit = self.get_control_value("velocity_limit_24h", 5)
        high_risk = self.get_control_value("velocity_high_risk", 10)
        risk1 = self.get_control_value("velocity_tier1_risk", 0.25)
        risk2 = self.get_control_value("velocity_tier2_risk", 0.50)
        
        tx_count_24h = customer.get_tx_count_24h()
        
        if tx_count_24h > high_risk:
            risk_contribution += risk2
            triggered_rules.append(f"velocity_exceeds_{high_risk}_24h")
        elif tx_count_24h > limit:
            risk_contribution += risk1
            triggered_rules.append(f"velocity_exceeds_{limit}_24h")
        
        return {
            "rule_set": "velocity_rules",
            "risk_contribution": min(0.5, risk_contribution),
            "triggered_rules": triggered_rules,
            "tx_count_24h": tx_count_24h,
            "thresholds_applied": {"limit": limit, "high_risk": high_risk}
        }