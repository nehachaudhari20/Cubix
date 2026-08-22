"""
Payment Sandbox - Main entry point
Delegates action execution to the Orchestrator.
"""

from typing import Dict, Any, Optional

from .state import SandboxState, SyntheticCustomer, SyntheticDevice
from .schemas import ActionType, SandboxObservation
from .orchestrator import SandboxOrchestrator
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

        self.kyc_engine = KYCStateEngine(self.state)
        self.device_engine = DeviceEngine(self.state)
        self.auth_engine = AuthenticationEngine(self.state)
        self.risk_engine = RiskEngine(self.state)
        self.authz_engine = AuthorizationEngine(self.state)
        self.settlement_engine = SettlementEngine(self.state)

        if ml_model:
            self.risk_engine.set_ml_model(ml_model)

        self.orchestrator = SandboxOrchestrator(
            state=self.state,
            kyc_engine=self.kyc_engine,
            device_engine=self.device_engine,
            auth_engine=self.auth_engine,
            risk_engine=self.risk_engine,
            authz_engine=self.authz_engine,
            settlement_engine=self.settlement_engine,
        )

    def execute(self, action_type: str, payload: Dict[str, Any]) -> SandboxObservation:
        """Execute a single action via the Orchestrator."""
        return self.orchestrator.execute(action_type, payload)

    def process_transaction(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a payment through the full lifecycle.
        Backward-compatible wrapper around initiate_payment action.
        """
        observation = self.execute(ActionType.INITIATE_PAYMENT.value, transaction)
        return observation.to_legacy_response()

    # ============================================================
    # Helper Methods for Seeding (convenience wrappers)
    # ============================================================

    def add_customer(self, customer_id: str, name: str, pan: str, dob: str,
                     address: str, trust_score: float = 0.5) -> SyntheticCustomer:
        observation = self.execute(ActionType.REGISTER_CUSTOMER.value, {
            "customer_id": customer_id,
            "name": name,
            "pan": pan,
            "dob": dob,
            "address": address,
            "trust_score": trust_score,
        })
        return self.state.customers[customer_id]

    def add_device(self, device_id: str, customer_id: str,
                   fingerprint: Dict = None) -> SyntheticDevice:
        self.execute(ActionType.REGISTER_DEVICE.value, {
            "device_id": device_id,
            "customer_id": customer_id,
            "fingerprint": fingerprint or {},
        })
        return self.state.devices[device_id]

    def get_state(self) -> SandboxState:
        """Return the current state for inspection."""
        return self.state

    def get_execution_log(self):
        """Return the orchestrator execution log."""
        return self.orchestrator.execution_log
