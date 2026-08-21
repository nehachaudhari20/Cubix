"""Merchant-Based Static Rules"""

from typing import Dict, Any


class MerchantRules:
    """Rules based on merchant characteristics."""
    
    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate merchant-based rules."""
        risk_contribution = 0.0
        triggered_rules = []
        
        merchant_risk = features.get("merchant_risk", 0.3)
        
        if merchant_risk > 0.7:
            risk_contribution += 0.25
            triggered_rules.append("merchant_high_risk")
        
        if merchant_risk > 0.9:
            risk_contribution += 0.25
            triggered_rules.append("merchant_very_high_risk")
        
        return {
            "rule_set": "merchant_rules",
            "risk_contribution": min(0.5, risk_contribution),
            "triggered_rules": triggered_rules,
            "merchant_risk": merchant_risk
        }