"""Amount-Based Static Rules"""

from typing import Dict, Any


class AmountRules:
    """Rules based on transaction amounts."""
    
    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate amount-based rules."""
        amount = features.get("amount", 0)
        risk_contribution = 0.0
        triggered_rules = []
        
        # Tier 1: Amount > 25,000
        if amount > 25000:
            risk_contribution += 0.25
            triggered_rules.append("amount_exceeds_25000")
        
        # Tier 2: Amount > 50,000
        if amount > 50000:
            risk_contribution += 0.25
            triggered_rules.append("amount_exceeds_50000")
        
        # Tier 3: Amount > 100,000
        if amount > 100000:
            risk_contribution += 0.25
            triggered_rules.append("amount_exceeds_100000")
        
        return {
            "rule_set": "amount_rules",
            "risk_contribution": min(0.75, risk_contribution),
            "triggered_rules": triggered_rules,
            "amount": amount
        }