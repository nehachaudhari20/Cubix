"""Amount-Based Static Rules with KB API Integration"""

from typing import Dict, Any
from .base import BaseRule


class AmountRules(BaseRule):
    """Rules based on transaction amounts."""
    
    def __init__(self):
        super().__init__("Payment Initiation")
    
    def _get_default_controls(self) -> Dict[str, Any]:
        """Fallback default controls."""
        return {
            "amount_limit_tier1": 25000,
            "amount_limit_tier2": 50000,
            "amount_limit_tier3": 100000,
            "amount_tier1_risk": 0.25,
            "amount_tier2_risk": 0.25,
            "amount_tier3_risk": 0.25
        }
    
    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate amount-based rules using KB controls."""
        amount = features.get("amount", 0)
        risk_contribution = 0.0
        triggered_rules = []
        
        # Fetch thresholds from KB API
        tier1 = self.get_control_value("amount_limit_tier1", 25000)
        tier2 = self.get_control_value("amount_limit_tier2", 50000)
        tier3 = self.get_control_value("amount_limit_tier3", 100000)
        risk1 = self.get_control_value("amount_tier1_risk", 0.25)
        risk2 = self.get_control_value("amount_tier2_risk", 0.25)
        risk3 = self.get_control_value("amount_tier3_risk", 0.25)
        
        # Apply rules
        if amount > tier3:
            risk_contribution += risk3
            triggered_rules.append(f"amount_exceeds_{tier3}")
        
        if amount > tier2:
            risk_contribution += risk2
            triggered_rules.append(f"amount_exceeds_{tier2}")
        
        if amount > tier1:
            risk_contribution += risk1
            triggered_rules.append(f"amount_exceeds_{tier1}")
        
        return {
            "rule_set": "amount_rules",
            "risk_contribution": min(0.75, risk_contribution),
            "triggered_rules": triggered_rules,
            "amount": amount,
            "thresholds_applied": {"tier1": tier1, "tier2": tier2, "tier3": tier3}
        }