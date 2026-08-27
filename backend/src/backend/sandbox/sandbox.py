"""
Payment Sandbox - Main entry point
Delegates action execution to the Orchestrator.
"""

import os
from typing import Dict, Any, Optional

from .state import (
    SandboxState,
    SyntheticCustomer,
    SyntheticDevice,
    SyntheticMerchant,
    SyntheticBeneficiary,
    SyntheticAccount,
)
from .schemas import ActionType, SandboxObservation
from .orchestrator import SandboxOrchestrator
from .engines.kyc import KYCStateEngine
from .engines.device import DeviceEngine
from .engines.auth import AuthenticationEngine
from .engines.account_merchant import AccountMerchantEngine
from .engines.payment_initiation import PaymentInitiationEngine
from .engines.risk import RiskEngine
from .engines.authorization import AuthorizationEngine
from .engines.settlement import SettlementEngine
from .rules.compiled_controls import CompiledControlSet, set_global_compiled_controls
from .rules.control_compiler import ControlCompiler


class PaymentSandbox:
    """The main Payment Sandbox engine."""

    def __init__(
        self,
        state: Optional[SandboxState] = None,
        ml_model: Any = None,
        compiled_controls: Optional[CompiledControlSet] = None,
        kb_path: str = "data/knowledge/canonical",
    ):
        self.state = state or SandboxState()
        self.compiled_controls = compiled_controls or ControlCompiler(kb_path).compile()
        set_global_compiled_controls(self.compiled_controls)

        self.kyc_engine = KYCStateEngine(self.state)
        self.device_engine = DeviceEngine(self.state)
        self.auth_engine = AuthenticationEngine(self.state)
        self.account_merchant_engine = AccountMerchantEngine(self.state)
        self.payment_initiation_engine = PaymentInitiationEngine(self.state)
        self.risk_engine = RiskEngine(self.state, compiled_controls=self.compiled_controls)
        self.authz_engine = AuthorizationEngine(self.state, compiled_controls=self.compiled_controls)
        self.settlement_engine = SettlementEngine(self.state)

        if ml_model is not None:
            self.risk_engine.set_ml_model(ml_model)
        elif os.environ.get("FRAUDSHIELD_ENABLED", "true").lower() in ("1", "true", "yes"):
            self._try_load_fraudshield()

        self.orchestrator = SandboxOrchestrator(
            state=self.state,
            kyc_engine=self.kyc_engine,
            device_engine=self.device_engine,
            auth_engine=self.auth_engine,
            account_merchant_engine=self.account_merchant_engine,
            payment_initiation_engine=self.payment_initiation_engine,
            risk_engine=self.risk_engine,
            authz_engine=self.authz_engine,
            settlement_engine=self.settlement_engine,
            compiled_controls=self.compiled_controls,
        )

    def execute(self, action_type: str, payload: Dict[str, Any]) -> SandboxObservation:
        """Execute a single action via the Orchestrator."""
        return self.orchestrator.execute(action_type, payload)

    def _try_load_fraudshield(self):
        """Auto-load FraudShield and anomaly scorer from data/models if present."""
        try:
            from backend.blue_team.fraudshield import load_fraudshield
            from backend.blue_team.anomaly import load_anomaly_scorer

            model = load_fraudshield()
            if model:
                self.risk_engine.set_ml_model(model)

            scorer = load_anomaly_scorer()
            if scorer:
                self.risk_engine.set_anomaly_scorer(scorer)
        except Exception:
            pass

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
        self.execute(ActionType.REGISTER_CUSTOMER.value, {
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

    def open_account(self, account_id: str, customer_id: str,
                     balance: float = 50000.0) -> SyntheticAccount:
        self.execute(ActionType.OPEN_ACCOUNT.value, {
            "account_id": account_id,
            "customer_id": customer_id,
            "balance": balance,
        })
        return self.state.accounts[account_id]

    def onboard_merchant(self, merchant_id: str, name: str, mcc: str = "5411",
                         declared_mcc: str = None, kyb_verified: bool = True,
                         risk_score: float = 0.3, owner_customer_id: str = None) -> SyntheticMerchant:
        self.execute(ActionType.ONBOARD_MERCHANT.value, {
            "merchant_id": merchant_id,
            "name": name,
            "mcc": mcc,
            "declared_mcc": declared_mcc or mcc,
            "kyb_verified": kyb_verified,
            "risk_score": risk_score,
            "owner_customer_id": owner_customer_id,
        })
        return self.state.merchants[merchant_id]

    def link_beneficiary(self, beneficiary_id: str, customer_id: str,
                         name: str = "Payee", account_ref: str = None) -> SyntheticBeneficiary:
        self.execute(ActionType.LINK_BENEFICIARY.value, {
            "beneficiary_id": beneficiary_id,
            "customer_id": customer_id,
            "name": name,
            "account_ref": account_ref or f"ACC-{beneficiary_id}",
        })
        return self.state.beneficiaries[beneficiary_id]

    def get_state(self) -> SandboxState:
        """Return the current state for inspection."""
        return self.state

    def get_execution_log(self):
        """Return the orchestrator execution log."""
        return self.orchestrator.execution_log
