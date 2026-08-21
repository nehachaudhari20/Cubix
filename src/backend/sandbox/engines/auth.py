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
        # 95% success rate for legitimate auth, 60% for suspicious
        success_rate = 0.95
        customer = self.state.get_customer(customer_id)
        
        if customer and customer.trust_score < 0.3:
            success_rate = 0.60  # Low trust = harder to auth
        
        success = random.random() < success_rate
        
        return {
            "status": "PASS" if success else "FAIL",
            "method": method,
            "message": "Authentication successful" if success else "Authentication failed"
        }