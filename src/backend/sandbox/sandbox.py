"""
Payment Sandbox - Main Orchestrator
Processes transaction requests through the full payment lifecycle.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from .state import SandboxState, SyntheticCustomer, SyntheticDevice
from .engines.kyc import KYCStateEngine
from .engines.device import DeviceEngine
from .engines.auth import AuthenticationEngine
from .engines.risk import RiskEngine
from .engines.authorization import AuthorizationEngine
from .engines.settlement import SettlementEngine


class PaymentSandbox:
    """The main Payment Sandbox engine."""
    
    def __init__(self, state: Optional[SandboxState] = None, ml_model: Any = None):
        self.state = state or SandboxState()
        
        # Initialize engines
        self.kyc_engine = KYCStateEngine(self.state)
        self.device_engine = DeviceEngine(self.state)
        self.auth_engine = AuthenticationEngine(self.state)
        self.risk_engine = RiskEngine(self.state)
        self.authz_engine = AuthorizationEngine(self.state)
        self.settlement_engine = SettlementEngine(self.state)
        
        # Inject ML model
        if ml_model:
            self.risk_engine.set_ml_model(ml_model)
        
        self.transaction_history = []
    
    def process_transaction(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point: process a transaction through the sandbox.
        Returns the final decision with full journey trace.
        """
        transaction_id = transaction.get("transaction_id", f"txn_{uuid.uuid4().hex[:8]}")
        customer_id = transaction.get("customer_id")
        device_id = transaction.get("device_id", f"dev_{uuid.uuid4().hex[:8]}")
        
        journey = []
        
        # ============================================================
        # STEP 1: KYC Check
        # ============================================================
        kyc_result = self.kyc_engine.verify(customer_id)
        journey.append({"step": "KYC", "result": kyc_result})
        
        if kyc_result["status"] == "FAIL":
            return self._final_response(transaction_id, "BLOCK", "kyc_failed", journey, {})
        
        # ============================================================
        # STEP 2: Device Check
        # ============================================================
        device_result = self.device_engine.check_device(device_id, customer_id)
        journey.append({"step": "Device", "result": device_result})
        
        # Update transaction with device info
        transaction["is_new_device"] = device_result.get("is_new", True)
        transaction["device_age_days"] = device_result.get("device_age_days", 0)
        
        # ============================================================
        # STEP 3: Authentication
        # ============================================================
        auth_method = transaction.get("authentication_method", "otp")
        auth_result = self.auth_engine.authenticate(customer_id, auth_method)
        journey.append({"step": "Authentication", "result": auth_result})
        
        if auth_result["status"] == "FAIL":
            return self._final_response(transaction_id, "BLOCK", "auth_failed", journey, {})
        
        # ============================================================
        # STEP 4: Risk Scoring
        # ============================================================
        risk_result = self.risk_engine.score(transaction)
        journey.append({"step": "Risk", "result": risk_result})
        
        # ============================================================
        # STEP 5: Authorization
        # ============================================================
        authz_result = self.authz_engine.authorize(risk_result, transaction)
        journey.append({"step": "Authorization", "result": authz_result})
        
        # ============================================================
        # STEP 6: Settlement (if authorized)
        # ============================================================
        settlement_result = None
        if authz_result["decision"] == "ALLOW":
            settlement_result = self.settlement_engine.settle(transaction, authz_result)
            journey.append({"step": "Settlement", "result": settlement_result})
        
        # ============================================================
        # Update state with transaction
        # ============================================================
        self.state.add_transaction(transaction)
        
        # ============================================================
        # Final Response
        # ============================================================
        return self._final_response(
            transaction_id,
            authz_result["decision"],
            authz_result["reason"],
            journey,
            {
                "risk_score": risk_result.get("risk_score", 0),
                "ml_score": risk_result.get("ml_score", 0),
                "rule_risk": risk_result.get("rule_risk", 0),
                "settled": settlement_result is not None,
                "settlement_detail": settlement_result
            }
        )
    
    def _final_response(self, txn_id: str, decision: str, reason: str,
                        journey: list, state: dict) -> Dict[str, Any]:
        """Build final sandbox response."""
        return {
            "transaction_id": txn_id,
            "decision": decision,
            "reason": reason,
            "message": f"Transaction {decision.lower()}ed: {reason}",
            "journey": journey,
            "state": state,
            "timestamp": datetime.now().isoformat()
        }
    
    # ============================================================
    # Helper Methods for Seeding
    # ============================================================
    
    def add_customer(self, customer_id: str, name: str, pan: str, dob: str,
                     address: str, trust_score: float = 0.5) -> SyntheticCustomer:
        customer = SyntheticCustomer(
            customer_id=customer_id,
            name=name,
            pan=pan,
            dob=dob,
            address=address,
            created_at=datetime.now(),
            verified=True,
            trust_score=trust_score,
            account_age_days=0
        )
        self.state.customers[customer_id] = customer
        return customer
    
    def add_device(self, device_id: str, customer_id: str,
                   fingerprint: Dict = None) -> SyntheticDevice:
        device = SyntheticDevice(
            device_id=device_id,
            customer_id=customer_id,
            fingerprint=fingerprint or {},
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            is_known=True
        )
        self.state.devices[device_id] = device
        return device
    
    def get_state(self) -> SandboxState:
        """Return the current state for inspection."""
        return self.state