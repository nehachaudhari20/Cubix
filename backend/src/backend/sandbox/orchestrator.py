"""
Sandbox Orchestrator
Routes individual attack actions to the correct lifecycle engine(s).
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List

from .schemas import ActionType, JourneyStep, SandboxObservation
from .state import SandboxState, SyntheticCustomer, SyntheticDevice
from .rules.compiled_controls import CompiledControlSet
from .engines.kyc import KYCStateEngine
from .engines.device import DeviceEngine
from .engines.auth import AuthenticationEngine
from .engines.account_merchant import AccountMerchantEngine
from .engines.payment_initiation import PaymentInitiationEngine
from .engines.risk import RiskEngine
from .engines.authorization import AuthorizationEngine
from .engines.settlement import SettlementEngine
from .engines.genai_context import GenAIContextEngine
from .engines.gateway import GatewayEngine
from .engines.aml_compliance import AMLComplianceEngine
from .engines.beneficiary_check import BeneficiaryCheckEngine
from .engines.acquirer import AcquirerEngine
from .engines.mule_cashout import MuleCashoutEngine
from .lifecycle_router import resolve_payment_path
from .lifecycle_engine_registry import PAYMENT_PATHS, JOURNEY_STEP_NAMES, payment_path_engines


class SandboxOrchestrator:
    """Routes actions to engines and returns structured observations."""

    def __init__(
        self,
        state: SandboxState,
        kyc_engine: KYCStateEngine,
        device_engine: DeviceEngine,
        auth_engine: AuthenticationEngine,
        account_merchant_engine: AccountMerchantEngine,
        payment_initiation_engine: PaymentInitiationEngine,
        risk_engine: RiskEngine,
        authz_engine: AuthorizationEngine,
        settlement_engine: SettlementEngine,
        genai_engine: GenAIContextEngine | None = None,
        gateway_engine: GatewayEngine | None = None,
        aml_engine: AMLComplianceEngine | None = None,
        beneficiary_engine: BeneficiaryCheckEngine | None = None,
        acquirer_engine: AcquirerEngine | None = None,
        mule_engine: MuleCashoutEngine | None = None,
        compiled_controls: CompiledControlSet | None = None,
    ):
        self.state = state
        self.compiled_controls = compiled_controls
        self.kyc_engine = kyc_engine
        self.device_engine = device_engine
        self.auth_engine = auth_engine
        self.account_merchant_engine = account_merchant_engine
        self.payment_initiation_engine = payment_initiation_engine
        self.risk_engine = risk_engine
        self.authz_engine = authz_engine
        self.settlement_engine = settlement_engine
        self.genai_engine = genai_engine or GenAIContextEngine()
        self.gateway_engine = gateway_engine or GatewayEngine(state)
        self.aml_engine = aml_engine or AMLComplianceEngine(state)
        self.beneficiary_engine = beneficiary_engine or BeneficiaryCheckEngine(state)
        self.acquirer_engine = acquirer_engine or AcquirerEngine(state)
        self.mule_engine = mule_engine or MuleCashoutEngine(state)
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
            ActionType.OPEN_ACCOUNT.value: self._open_account,
            ActionType.ONBOARD_MERCHANT.value: self._onboard_merchant,
            ActionType.LINK_BENEFICIARY.value: self._link_beneficiary,
            ActionType.INITIATE_PAYMENT.value: self._initiate_payment,
            ActionType.SIMULATE_GENAI_CONTEXT.value: self._simulate_genai_context,
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
        age_days = int(payload.get("account_age_days", 0))
        if age_days > 0:
            from datetime import timedelta
            customer.created_at = datetime.now() - timedelta(days=age_days)
            customer.account_age_days = age_days
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

    def _open_account(self, action_id: str, payload: Dict[str, Any], timestamp: str) -> SandboxObservation:
        result = self.account_merchant_engine.open_account(payload)
        passed = result.get("status") == "PASS"
        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.OPEN_ACCOUNT.value,
            decision="PASS" if passed else "FAIL",
            reason=result.get("reason", "account_opened" if passed else "account_failed"),
            message=result.get("message", ""),
            journey=[JourneyStep(step="Account", result=result)],
            state_snapshot={"account_id": payload.get("account_id"), "customer_id": payload.get("customer_id")},
            timestamp=timestamp,
        )

    def _onboard_merchant(self, action_id: str, payload: Dict[str, Any], timestamp: str) -> SandboxObservation:
        result = self.account_merchant_engine.onboard_merchant(payload)
        passed = result.get("status") == "PASS"
        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.ONBOARD_MERCHANT.value,
            decision="PASS" if passed else "FAIL",
            reason=result.get("reason", "merchant_onboarded" if passed else "merchant_failed"),
            message=result.get("message", ""),
            journey=[JourneyStep(step="Account/Merchant", result=result)],
            state_snapshot={
                "merchant_id": payload.get("merchant_id"),
                "mcc": result.get("mcc"),
                "risk_score": result.get("risk_score"),
            },
            timestamp=timestamp,
        )

    def _link_beneficiary(self, action_id: str, payload: Dict[str, Any], timestamp: str) -> SandboxObservation:
        result = self.account_merchant_engine.link_beneficiary(payload)
        passed = result.get("status") == "PASS"
        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.LINK_BENEFICIARY.value,
            decision="PASS" if passed else "FAIL",
            reason=result.get("reason", "beneficiary_linked" if passed else "beneficiary_failed"),
            message=result.get("message", ""),
            journey=[JourneyStep(step="Beneficiary", result=result)],
            state_snapshot={
                "beneficiary_id": payload.get("beneficiary_id"),
                "customer_id": payload.get("customer_id"),
            },
            timestamp=timestamp,
        )

    def _simulate_genai_context(
        self, action_id: str, payload: Dict[str, Any], timestamp: str
    ) -> SandboxObservation:
        """Simulate GenAI / social-engineering / agentic context (pre-payment or standalone)."""
        result = self.genai_engine.evaluate(payload, sandbox_state=self.state)
        features = result.get("genai_features") or {}
        triggers = list(result.get("triggered_rules") or [])
        risk = float(result.get("genai_risk_contribution") or 0)

        if self.compiled_controls is not None:
            triggers = self.compiled_controls.resolve_triggers(triggers)

        decision = "PASS"
        if risk >= 0.75:
            decision = "CHALLENGE"
        if risk >= 0.90:
            decision = "BLOCK"

        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.SIMULATE_GENAI_CONTEXT.value,
            decision=decision,
            reason="genai_context_evaluated",
            message=f"GenAI context scored {risk:.3f} ({len(triggers)} signals)",
            risk_score=round(risk, 4),
            control_triggers=triggers,
            journey=[JourneyStep(step="GenAI Context", result=result)],
            state_snapshot={
                "genai_features": features,
                "channels": result.get("channels") or [],
                "capability_ids": result.get("capability_ids") or [],
                "attack_family": payload.get("attack_family"),
            },
            timestamp=timestamp,
        )

    def _initiate_payment(
        self, action_id: str, payload: Dict[str, Any], timestamp: str
    ) -> SandboxObservation:
        """Route payment through KB-selected lifecycle engines (not always full chain)."""
        transaction = dict(payload)
        transaction_id = transaction.get("transaction_id", action_id)
        customer_id = transaction.get("customer_id")
        device_id = transaction.get("device_id", f"dev_{uuid.uuid4().hex[:8]}")

        path = resolve_payment_path(transaction)
        family_stage_engines = transaction.get("lifecycle_engines")
        stage_list = payment_path_engines(path, family_stage_engines)
        stages = stage_list  # ordered list preserves sequence

        journey: List[JourneyStep] = []
        control_triggers: List[str] = []

        if "agent_commerce" in stages and transaction.get("genai_features"):
            agent_result = {
                "status": "PASS",
                "engine": "agent_commerce",
                "genai_risk": transaction.get("genai_risk_contribution"),
                "note": "GenAI context pre-computed",
            }
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["agent_commerce"], result=agent_result))

        if "kyc" in stages:
            kyc_result = self.kyc_engine.verify(customer_id)
            journey.append(JourneyStep(step="KYC", result=kyc_result))
            if kyc_result["status"] == "FAIL":
                return self._payment_observation(
                    action_id, transaction_id, "BLOCK", "kyc_failed",
                    journey, control_triggers, timestamp, payment_path=path,
                )

        if "device" in stages:
            device_result = self.device_engine.check_device(device_id, customer_id)
            journey.append(JourneyStep(step="Device", result=device_result))
            transaction["is_new_device"] = device_result.get("is_new", True)
            transaction["is_unknown_device"] = device_result.get("is_unknown_device", False)
            transaction["device_age_days"] = device_result.get("device_age_days", 0)

        if "auth" in stages:
            auth_method = transaction.get("authentication_method", "otp")
            auth_result = self.auth_engine.authenticate(customer_id, auth_method)
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["auth"], result=auth_result))
            if auth_result["status"] == "FAIL":
                return self._payment_observation(
                    action_id, transaction_id, "BLOCK", "auth_failed",
                    journey, control_triggers, timestamp, payment_path=path,
                )

        if "beneficiary" in stages:
            ben_result = self.beneficiary_engine.check(transaction)
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["beneficiary"], result=ben_result))
            if ben_result.get("flags"):
                control_triggers.extend(ben_result["flags"])
            if ben_result["status"] == "FAIL":
                return self._payment_observation(
                    action_id, transaction_id, "BLOCK", "beneficiary_failed",
                    journey, control_triggers, timestamp, payment_path=path,
                )

        if "payment_init" in stages:
            pi_result = self.payment_initiation_engine.validate(transaction)
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["payment_init"], result=pi_result))
            if pi_result.get("flags"):
                control_triggers.extend(pi_result["flags"])
                transaction["payment_initiation_flags"] = pi_result["flags"]
            if pi_result["status"] == "FAIL":
                return self._payment_observation(
                    action_id, transaction_id, "BLOCK", "payment_initiation_failed",
                    journey, control_triggers, timestamp, payment_path=path,
                )

        if "gateway" in stages:
            gw_result = self.gateway_engine.process(transaction)
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["gateway"], result=gw_result))
            if gw_result.get("flags"):
                control_triggers.extend(gw_result["flags"])
            if gw_result["status"] == "FAIL":
                return self._payment_observation(
                    action_id, transaction_id, "BLOCK", "gateway_failed",
                    journey, control_triggers, timestamp, payment_path=path,
                )

        if "acquirer" in stages:
            acq_result = self.acquirer_engine.monitor(transaction)
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["acquirer"], result=acq_result))
            if acq_result.get("flags"):
                control_triggers.extend(acq_result["flags"])
            if acq_result["status"] == "FAIL":
                return self._payment_observation(
                    action_id, transaction_id, "BLOCK", "acquirer_failed",
                    journey, control_triggers, timestamp, payment_path=path,
                )

        if "aml" in stages:
            aml_result = self.aml_engine.screen(transaction)
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["aml"], result=aml_result))
            if aml_result.get("flags"):
                control_triggers.extend(aml_result["flags"])
            transaction["aml_risk"] = aml_result.get("aml_risk")
            if aml_result["status"] == "FAIL":
                return self._payment_observation(
                    action_id, transaction_id, "BLOCK", "aml_failed",
                    journey, control_triggers, timestamp, payment_path=path,
                )

        if "mule" in stages:
            mule_result = self.mule_engine.evaluate(transaction)
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["mule"], result=mule_result))
            if mule_result.get("flags"):
                control_triggers.extend(mule_result["flags"])
            if mule_result["status"] == "FAIL":
                return self._payment_observation(
                    action_id, transaction_id, "BLOCK", "mule_cashout_blocked",
                    journey, control_triggers, timestamp, payment_path=path,
                )

        if transaction.get("genai_features"):
            transaction["genai_context"] = transaction["genai_features"]

        # Journey correlation + expected controls for data-driven RuleEngine
        transaction["journey"] = journey
        transaction["control_triggers"] = list(control_triggers)
        expected = self._resolve_expected_controls(transaction)
        if expected:
            transaction["expected_controls"] = expected
            transaction["targeted_control_ids"] = expected

        risk_result = self.risk_engine.score(transaction)
        journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["risk"], result=risk_result))
        for rule in risk_result.get("rule_details", []):
            control_triggers.extend(rule.get("triggered_rules", []))
        control_triggers.extend(risk_result.get("triggered_controls") or [])

        authz_result = self.authz_engine.authorize(risk_result, transaction)
        journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["authz"], result=authz_result))
        decision = authz_result["decision"]
        reason = authz_result["reason"]

        settlement_result = None
        settled = False
        if decision == "ALLOW" and "settlement" in stages:
            settlement_result = self.settlement_engine.settle(transaction, authz_result)
            journey.append(JourneyStep(step=JOURNEY_STEP_NAMES["settlement"], result=settlement_result))
            settled = settlement_result is not None and settlement_result.get("status") == "SETTLED"

        transaction["transaction_id"] = transaction_id
        transaction["payment_path"] = path
        self.state.add_transaction(transaction)

        state_snapshot = {"payment_path": path}
        customer = self.state.get_customer(customer_id)
        if customer:
            state_snapshot.update({
                "customer_id": customer_id,
                "trust_score": customer.trust_score,
                "tx_count_24h": customer.get_tx_count_24h(),
            })
        if transaction.get("genai_features"):
            state_snapshot["genai_features"] = transaction["genai_features"]
        if risk_result.get("control_gaps"):
            state_snapshot["control_gaps"] = risk_result["control_gaps"]
        if risk_result.get("journey_features"):
            state_snapshot["journey_features"] = risk_result["journey_features"]
        if risk_result.get("triggered_signals"):
            state_snapshot["triggered_signals"] = risk_result["triggered_signals"]

        if self.compiled_controls is not None:
            control_triggers = self.compiled_controls.resolve_triggers(control_triggers)

        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.INITIATE_PAYMENT.value,
            decision=decision,
            reason=reason,
            message=f"Transaction {decision.lower()}ed via {path}: {reason}",
            risk_score=risk_result.get("risk_score"),
            ml_score=risk_result.get("ml_score"),
            rule_risk=risk_result.get("rule_risk"),
            anomaly_score=risk_result.get("anomaly_score"),
            control_triggers=control_triggers,
            journey=journey,
            state_snapshot=state_snapshot,
            timestamp=timestamp,
            transaction_id=transaction_id,
            settled=settled,
            settlement_detail=settlement_result,
        )

    def _resolve_expected_controls(self, transaction: Dict[str, Any]) -> List[str]:
        """Load expected/targeted controls from payload or KB family."""
        direct = transaction.get("expected_controls") or transaction.get("targeted_control_ids")
        family_id = transaction.get("attack_family") or transaction.get("family_id")
        family = None
        if family_id:
            try:
                from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader

                family = CanonicalKnowledgeLoader().get_family(family_id)
            except Exception:
                family = None
        if family:
            if not transaction.get("family_signal_ids") and not transaction.get("observable_signal_ids"):
                transaction["family_signal_ids"] = list(family.get("observable_signal_ids") or [])
            if not direct:
                direct = list(family.get("targeted_control_ids") or [])
            # Pass full family for richer GenAI/rule context
            transaction.setdefault("family", family)
        return list(direct or [])

    def _payment_observation(
        self,
        action_id: str,
        transaction_id: str,
        decision: str,
        reason: str,
        journey: List[JourneyStep],
        control_triggers: List[str],
        timestamp: str,
        payment_path: str = "full",
    ) -> SandboxObservation:
        if self.compiled_controls is not None:
            control_triggers = self.compiled_controls.resolve_triggers(control_triggers)
        return SandboxObservation(
            action_id=action_id,
            action_type=ActionType.INITIATE_PAYMENT.value,
            decision=decision,
            reason=reason,
            message=f"Transaction {decision.lower()}ed via {payment_path}: {reason}",
            control_triggers=control_triggers,
            journey=journey,
            state_snapshot={"payment_path": payment_path},
            timestamp=timestamp,
            transaction_id=transaction_id,
        )
