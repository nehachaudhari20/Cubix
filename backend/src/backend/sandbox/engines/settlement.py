"""Settlement Simulator Engine"""

import random
from typing import Dict, Any
from ..state import SandboxState


class SettlementEngine:
    """Post-authorization settlement simulator."""
    
    def __init__(self, state: SandboxState):
        self.state = state
    
    def settle(self, transaction: Dict[str, Any], auth_result: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate settlement after authorization."""
        if auth_result.get("decision") != "ALLOW":
            return {
                "status": "FAIL",
                "reason": "not_authorized",
                "message": "Transaction was not authorized"
            }
        
        # Simulate settlement time
        rail = transaction.get("payment_rail", "upi")
        settlement_times = {
            "upi": "instant",
            "card": f"{random.randint(1, 3)} days",
            "bank_transfer": f"{random.randint(1, 2)} days",
            "wallet": "instant",
            "crypto": f"{random.randint(0, 2)} minutes"
        }
        settlement_time = settlement_times.get(rail, "1 day")
        
        return {
            "status": "SETTLED",
            "settlement_time": settlement_time,
            "amount": transaction.get("amount"),
            "transaction_id": transaction.get("transaction_id")
        }