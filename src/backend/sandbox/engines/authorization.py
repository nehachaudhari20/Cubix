"""Authorization Engine — Final Decision"""

from typing import Dict, Any
from ..state import SandboxState


class AuthorizationEngine:
    """Final authorization decision engine."""
    
    def __init__(self, state: SandboxState):
        self.state = state
    
    def authorize(self, risk_result: Dict[str, Any], transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Make final ALLOW/BLOCK/CHALLENGE decision."""
        risk_score = risk_result.get("risk_score", 0.5)
        
        # Thresholds (synthetic, not real Mastercard thresholds)
        if risk_score < 0.30:
            decision = "ALLOW"
            reason = "low_risk"
        elif risk_score < 0.60:
            decision = "CHALLENGE"
            reason = "medium_risk_step_up"
        else:
            decision = "BLOCK"
            reason = "high_risk"
        
        # Check velocity via customer history
        customer_id = transaction.get("customer_id")
        if customer_id:
            customer = self.state.get_customer(customer_id)
            if customer and customer.get_tx_count_24h() >= 5:
                decision = "BLOCK"
                reason = "velocity_exceeded"
        
        return {
            "decision": decision,
            "reason": reason,
            "risk_score": risk_score,
            "threshold_applied": 0.30 if risk_score < 0.30 else (0.60 if risk_score < 0.60 else 0.60)
        }