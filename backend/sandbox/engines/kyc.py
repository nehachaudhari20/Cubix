"""KYC Verification Engine"""

from typing import Dict, Any
from ..state import SandboxState


class KYCStateEngine:
    """KYC verification engine."""
    
    def __init__(self, state: SandboxState):
        self.state = state
    
    def verify(self, customer_id: str) -> Dict[str, Any]:
        """Verify a customer's identity."""
        customer = self.state.get_customer(customer_id)
        
        if not customer:
            return {
                "status": "FAIL",
                "reason": "customer_not_found",
                "message": "Customer not found in KYC registry"
            }
        
        if not customer.verified:
            return {
                "status": "FAIL",
                "reason": "unverified_customer",
                "message": "Customer is not verified"
            }
        
        return {
            "status": "PASS",
            "customer_id": customer_id,
            "trust_score": customer.trust_score,
            "account_age_days": customer.account_age_days
        }