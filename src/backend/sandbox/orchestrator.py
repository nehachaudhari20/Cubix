"""
Sandbox Orchestrator
Routes individual attack actions to the correct lifecycle engine(s).
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List

from .schemas import ActionType, JourneyStep, SandboxObservation
from .state import SandboxState, SyntheticCustomer, SyntheticDevice
from .engines.kyc import KYCStateEngine
from .engines.device import DeviceEngine
from .engines.auth import AuthenticationEngine
from .engines.risk import RiskEngine
from .engines.authorization import AuthorizationEngine
from .engines.settlement import SettlementEngine


class SandboxOrchestrator:
    """Routes actions to engines and returns structured observations."""

    def __init__(
        self,
        state: SandboxState,
        kyc_engine: KYCStateEngine,
        device_engine: DeviceEngine,
        auth_engine: AuthenticationEngine,
        risk_engine: RiskEngine,
        authz_engine: AuthorizationEngine,
        settlement_engine: SettlementEngine,
    ):
        self.state = state
        self.kyc_engine = kyc_engine
        self.device_engine = device_engine
        self.auth_engine = auth_engine
        self.risk_engine = risk_engine
        self.authz_engine = authz_engine
        self.settlement_engine = settlement_engine
        self.execution_log: List[Dict[str, Any]] = []

    def execute(self, action_type: str, payload: Dict[str, Any]) -> SandboxObservation:
        """Route an action to the appropriate engine handler."""
        action_id = payload.get("action_id") or payload.get("transaction_id") or f"act_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now().isoformat()

        handlers = {
            ActionType.REGISTER_CUSTOMER.value: self._register_customer,
            ActionType.REGISTER_DEVICE.value: self._register_device,
            ActionType.VERIFY_KYC.value: self._verify_kyc,
            ActionType.AUTHENTICATE.value: self._authenticate,
            ActionType.INITIATE_PAYMENT.value: self._initiate_payment,
        }

        handler = handlers.get(action_type)
        if not handler:
            observation = SandboxObservation(
                action_id=action_id,
                action_type=action_type,
                decision="FAIL",
                reason="unknown_action_type",
                message=f"Unknown action type: {action_type}",
                timestamp=timestamp,
            )
            self._record(action_type, payload, observation)
            return observation

        observation = handler(action_id, payload, timestamp)
        self._record(action_type, payload, observation)
        return observation

    def _record(self, action_type: str, payload: Dict[str, Any], observation: SandboxObservation) -> None:
        self.execution_log.append(
            {
                "action_type": action_type,
                "payload": payload,
                "observation": observation.model_dump(),
                "recorded_at": datetime.now().isoformat(),
            }
        )

    def _register_customer(
        self, action_id: str, payload: Dict[str, Any], timestamp: str
    ) -> SandboxObservation:
        customer_id = payload.get("customer_id")
        if not customer_id:
            return SandboxObservation(
                action_id=action_id,
                action_type=ActionType.REGISTER_CUSTOMER.value,
                decision="FAIL",
                reason="missing_customer_id",
                message="customer_id is required",
                timestamp=timestamp,
            )

        if self.state.get_customer(customer_id):
            return SandboxObservation(
                action_id=action_id,
                action_type=ActionType.REGISTER_CUSTOMER.value,
                decision="FAIL",
                reason="customer_already_exists",
                message=f"Customer {customer_id} already registered",
                timestamp=timestamp,
                state_snapshot={"customer_id": customer_id},
            )

        customer = SyntheticCustomer(
            customer_id=customer_id,
            name=payload.get("name", "Synthetic Customer"),
            pan=payload.get("pan", "SYN0000000"),
            dob=payload.get("dob", "1990-01-01"),
            address=payload.get("address", "Synthetic Address"),
            created_at=datetime.now(),
            verified=payload.get("verified", True),
            trust_score=float(payload.get("trust_score", 0.5)),
            account_age_days=int(payload.get("account_age_days", 0)),
        )
        self.state.customers[customer_id] = customer

        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.REGISTER_CUSTOMER.value,
            decision="PASS",
            reason="customer_registered",
            message=f"Customer {customer_id} registered",
            journey=[JourneyStep(step="Identity/KYC", result={"status": "PASS", "customer_id": customer_id})],
            state_snapshot={"customer_id": customer_id, "trust_score": customer.trust_score},
            timestamp=timestamp,
        )

    def _register_device(
        self, action_id: str, payload: Dict[str, Any], timestamp: str
    ) -> SandboxObservation:
        device_id = payload.get("device_id")
        customer_id = payload.get("customer_id")

        if not device_id or not customer_id:
            return SandboxObservation(
                action_id=action_id,
                action_type=ActionType.REGISTER_DEVICE.value,
                decision="FAIL",
                reason="missing_device_or_customer",
                message="device_id and customer_id are required",
                timestamp=timestamp,
            )

        if not self.state.get_customer(customer_id):
            return SandboxObservation(
                action_id=action_id,
                action_type=ActionType.REGISTER_DEVICE.value,
                decision="FAIL",
                reason="customer_not_found",
                message=f"Customer {customer_id} not found — register customer first",
                timestamp=timestamp,
            )

        device = SyntheticDevice(
            device_id=device_id,
            customer_id=customer_id,
            fingerprint=payload.get("fingerprint", {}),
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            is_known=True,
        )
        self.state.devices[device_id] = device

        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.REGISTER_DEVICE.value,
            decision="PASS",
            reason="device_registered",
            message=f"Device {device_id} registered for {customer_id}",
            journey=[JourneyStep(step="Device", result={"status": "PASS", "device_id": device_id})],
            state_snapshot={"device_id": device_id, "customer_id": customer_id},
            timestamp=timestamp,
        )

    def _verify_kyc(self, action_id: str, payload: Dict[str, Any], timestamp: str) -> SandboxObservation:
        customer_id = payload.get("customer_id")
        kyc_result = self.kyc_engine.verify(customer_id)
        passed = kyc_result.get("status") == "PASS"

        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.VERIFY_KYC.value,
            decision="PASS" if passed else "FAIL",
            reason=kyc_result.get("reason", "kyc_check"),
            message=kyc_result.get("message", ""),
            journey=[JourneyStep(step="KYC", result=kyc_result)],
            state_snapshot={"customer_id": customer_id},
            timestamp=timestamp,
        )

    def _authenticate(self, action_id: str, payload: Dict[str, Any], timestamp: str) -> SandboxObservation:
        customer_id = payload.get("customer_id")
        auth_method = payload.get("authentication_method", "otp")
        auth_result = self.auth_engine.authenticate(customer_id, auth_method)
        passed = auth_result.get("status") == "PASS"

        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.AUTHENTICATE.value,
            decision="PASS" if passed else "FAIL",
            reason="auth_success" if passed else "auth_failed",
            message=auth_result.get("message", ""),
            journey=[JourneyStep(step="Authentication", result=auth_result)],
            state_snapshot={"customer_id": customer_id, "method": auth_method},
            timestamp=timestamp,
        )

    def _initiate_payment(
        self, action_id: str, payload: Dict[str, Any], timestamp: str
    ) -> SandboxObservation:
        """Run full payment lifecycle: KYC → Device → Auth → Risk → Authz → Settlement."""
        transaction = dict(payload)
        transaction_id = transaction.get("transaction_id", action_id)
        customer_id = transaction.get("customer_id")
        device_id = transaction.get("device_id", f"dev_{uuid.uuid4().hex[:8]}")

        journey: List[JourneyStep] = []
        control_triggers: List[str] = []

        kyc_result = self.kyc_engine.verify(customer_id)
        journey.append(JourneyStep(step="KYC", result=kyc_result))
        if kyc_result["status"] == "FAIL":
            return self._payment_observation(
                action_id, transaction_id, "BLOCK", "kyc_failed",
                journey, control_triggers, timestamp,
            )

        device_result = self.device_engine.check_device(device_id, customer_id)
        journey.append(JourneyStep(step="Device", result=device_result))
        transaction["is_new_device"] = device_result.get("is_new", True)
        transaction["is_unknown_device"] = device_result.get("is_unknown_device", False)
        transaction["device_age_days"] = device_result.get("device_age_days", 0)

        auth_method = transaction.get("authentication_method", "otp")
        auth_result = self.auth_engine.authenticate(customer_id, auth_method)
        journey.append(JourneyStep(step="Authentication", result=auth_result))
        if auth_result["status"] == "FAIL":
            return self._payment_observation(
                action_id, transaction_id, "BLOCK", "auth_failed",
                journey, control_triggers, timestamp,
            )

        risk_result = self.risk_engine.score(transaction)
        journey.append(JourneyStep(step="Risk", result=risk_result))
        for rule in risk_result.get("rule_details", []):
            control_triggers.extend(rule.get("triggered_rules", []))

        authz_result = self.authz_engine.authorize(risk_result, transaction)
        journey.append(JourneyStep(step="Authorization", result=authz_result))
        decision = authz_result["decision"]
        reason = authz_result["reason"]

        settlement_result = None
        settled = False
        if decision == "ALLOW":
            settlement_result = self.settlement_engine.settle(transaction, authz_result)
            journey.append(JourneyStep(step="Settlement", result=settlement_result))
            settled = settlement_result is not None and settlement_result.get("status") == "SETTLED"

        transaction["transaction_id"] = transaction_id
        self.state.add_transaction(transaction)

        state_snapshot = {}
        customer = self.state.get_customer(customer_id)
        if customer:
            state_snapshot = {
                "customer_id": customer_id,
                "trust_score": customer.trust_score,
                "tx_count_24h": customer.get_tx_count_24h(),
            }

        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.INITIATE_PAYMENT.value,
            decision=decision,
            reason=reason,
            message=f"Transaction {decision.lower()}ed: {reason}",
            risk_score=risk_result.get("risk_score"),
            ml_score=risk_result.get("ml_score"),
            rule_risk=risk_result.get("rule_risk"),
            control_triggers=control_triggers,
            journey=journey,
            state_snapshot=state_snapshot,
            timestamp=timestamp,
            transaction_id=transaction_id,
            settled=settled,
            settlement_detail=settlement_result,
        )

    def _payment_observation(
        self,
        action_id: str,
        transaction_id: str,
        decision: str,
        reason: str,
        journey: List[JourneyStep],
        control_triggers: List[str],
        timestamp: str,
    ) -> SandboxObservation:
        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.INITIATE_PAYMENT.value,
            decision=decision,
            reason=reason,
            message=f"Transaction {decision.lower()}ed: {reason}",
            control_triggers=control_triggers,
            journey=journey,
            timestamp=timestamp,
            transaction_id=transaction_id,
        )
