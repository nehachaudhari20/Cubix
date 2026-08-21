"""Velocity-Based Static Rules"""

from typing import Dict, Any
from datetime import datetime, timedelta
from ..state import SandboxState


class VelocityRules:
    """Rules based on transaction velocity."""
    
    def __init__(self):
        # No state needed; state is passed through features
        pass
    
    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate velocity-based rules."""
        risk_contribution = 0.0
        triggered_rules = []
        
        # Get customer and their transaction count
        customer = features.get("customer")
        if customer:
            tx_count_24h = customer.get_tx_count_24h()
            
            if tx_count_24h > 10:
                risk_contribution += 0.5
                triggered_rules.append("velocity_exceeds_10_24h")
            elif tx_count_24h > 5:
                risk_contribution += 0.25
                triggered_rules.append("velocity_exceeds_5_24h")
        
        return {
            "rule_set": "velocity_rules",
            "risk_contribution": min(0.5, risk_contribution),
            "triggered_rules": triggered_rules,
            "tx_count_24h": features.get("customer").get_tx_count_24h() if features.get("customer") else 0
        }