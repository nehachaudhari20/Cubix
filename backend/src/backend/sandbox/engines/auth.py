"""Authentication Simulator Engine"""

import random
from typing import Dict, Any
from ..state import SandboxState


class AuthenticationEngine:
    """Authentication simulator."""
    
    def __init__(self, state: SandboxState):
        self.state = state
    
    def authenticate(self, customer_id: str, method: str = "otp") -> Dict[str, Any]:
        """Simulate authentication."""
        customer = self.state.get_customer(customer_id)

        # Deterministic for trusted customers; stochastic for low-trust (attack scenarios)
        if customer and customer.trust_score >= 0.5:
            success = True
        elif customer and customer.trust_score < 0.3:
            success = random.random() < 0.60
        else:
            success = random.random() < 0.95

        return {
            "status": "PASS" if success else "FAIL",
            "method": method,
            "message": "Authentication successful" if success else "Authentication failed"
        }