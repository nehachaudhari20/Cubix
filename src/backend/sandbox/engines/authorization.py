"""Authorization Engine — Final Decision (KB-Connected)"""

from typing import Dict, Any
from ..state import SandboxState
from ..rules.base import BaseRule


class AuthorizationEngine:
    """Final authorization decision engine."""
    
    def __init__(self, state: SandboxState):
        self.state = state
        # Use BaseRule to fetch authorization thresholds from KB
        self.kb_rule = BaseRule("Authorization")
    
    def authorize(self, risk_result: Dict[str, Any], transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Make final ALLOW/BLOCK/CHALLENGE decision."""
        risk_score = risk_result.get("risk_score", 0.5)
        
        # Fetch thresholds from KB API
        allow_threshold = self.kb_rule.get_control_value("allow_threshold", 0.30)
        challenge_threshold = self.kb_rule.get_control_value("challenge_threshold", 0.60)
        
        if risk_score < allow_threshold:
            decision = "ALLOW"
            reason = "low_risk"
        elif risk_score < challenge_threshold:
            decision = "CHALLENGE"
            reason = "medium_risk_step_up"
        else:
            decision = "BLOCK"
            reason = "high_risk"
        
        # Check velocity via customer history
        customer_id = transaction.get("customer_id")
        if customer_id:
            customer = self.state.get_customer(customer_id)
            if customer:
                # Fetch velocity limit from KB
                velocity_limit = self.kb_rule.get_control_value("velocity_limit_24h", 5)
                if customer.get_tx_count_24h() >= velocity_limit:
                    decision = "BLOCK"
                    reason = "velocity_exceeded"
        
        return {
            "decision": decision,
            "reason": reason,
            "risk_score": risk_score,
            "thresholds_applied": {
                "allow": allow_threshold,
                "challenge": challenge_threshold
            }
        }