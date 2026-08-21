"""Merchant-Based Static Rules with KB API Integration"""

from typing import Dict, Any
from .base import BaseRule


class MerchantRules(BaseRule):
    """Rules based on merchant characteristics."""
    
    def __init__(self):
        super().__init__("Merchant")
    
    def _get_default_controls(self) -> Dict[str, Any]:
        return {
            "merchant_high_risk_threshold": 0.70,
            "merchant_very_high_risk_threshold": 0.90,
            "merchant_high_risk_contribution": 0.25,
            "merchant_very_high_risk_contribution": 0.25
        }
    
    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate merchant-based rules using KB controls."""
        risk_contribution = 0.0
        triggered_rules = []
        
        merchant_risk = features.get("merchant_risk", 0.3)
        
        # Fetch controls from KB API
        high_threshold = self.get_control_value("merchant_high_risk_threshold", 0.70)
        very_high_threshold = self.get_control_value("merchant_very_high_risk_threshold", 0.90)
        high_risk = self.get_control_value("merchant_high_risk_contribution", 0.25)
        very_high_risk = self.get_control_value("merchant_very_high_risk_contribution", 0.25)
        
        if merchant_risk > very_high_threshold:
            risk_contribution += very_high_risk
            triggered_rules.append("merchant_very_high_risk")
        
        if merchant_risk > high_threshold:
            risk_contribution += high_risk
            triggered_rules.append("merchant_high_risk")
        
        return {
            "rule_set": "merchant_rules",
            "risk_contribution": min(0.5, risk_contribution),
            "triggered_rules": triggered_rules,
            "merchant_risk": merchant_risk,
            "thresholds_applied": {
                "high_threshold": high_threshold,
                "very_high_threshold": very_high_threshold
            }
        }