"""
Sandbox Client — bridges Red Team payloads to PaymentSandbox actions.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from backend.sandbox import PaymentSandbox, ActionType, SandboxObservation


# Map plan step / payload action strings to sandbox ActionType values
ACTION_ALIASES = {
    "register_customer": ActionType.REGISTER_CUSTOMER.value,
    "register_device": ActionType.REGISTER_DEVICE.value,
    "verify_kyc": ActionType.VERIFY_KYC.value,
    "authenticate": ActionType.AUTHENTICATE.value,
    "open_account": ActionType.OPEN_ACCOUNT.value,
    "onboard_merchant": ActionType.ONBOARD_MERCHANT.value,
    "link_beneficiary": ActionType.LINK_BENEFICIARY.value,
    "initiate_payment": ActionType.INITIATE_PAYMENT.value,
    "payment": ActionType.INITIATE_PAYMENT.value,
    "simulate_genai_context": ActionType.SIMULATE_GENAI_CONTEXT.value,
}


class SandboxClient:
    """Executes Red Team action payloads against the real Payment Sandbox."""

    def __init__(self, sandbox: Optional[PaymentSandbox] = None):
        self.sandbox = sandbox or PaymentSandbox()

    def execute_action(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run one sandbox action and return a normalized observation dict."""
        normalized = ACTION_ALIASES.get(action_type, action_type)
        observation: SandboxObservation = self.sandbox.execute(normalized, payload)
        return self._sanitize(self._observation_to_response(observation))

    def execute_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Red Team payload (supports legacy and action-based formats)."""
        action_type = payload.get("action_type", ActionType.INITIATE_PAYMENT.value)
        action_payload = payload.get("action_payload")

        if action_payload is None:
            action_payload = self._legacy_payload_to_action(action_type, payload)

        return self.execute_action(action_type, action_payload)

    def _legacy_payload_to_action(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convert legacy transaction-only payloads to sandbox action dicts."""
        if action_type == ActionType.REGISTER_CUSTOMER.value:
            return {
                "customer_id": payload.get("customer_id"),
                "name": payload.get("customer_name", payload.get("name", "Synthetic Customer")),
                "pan": payload.get("pan", "SYN0000000"),
                "dob": payload.get("dob", "1990-01-01"),
                "address": payload.get("address", "Synthetic Address"),
                "trust_score": payload.get("trust_score", 0.5),
                "verified": payload.get("verified", True),
            }
        if action_type == ActionType.REGISTER_DEVICE.value:
            return {
                "device_id": payload.get("device_id"),
                "customer_id": payload.get("customer_id"),
                "fingerprint": payload.get("fingerprint", {}),
            }
        if action_type == ActionType.ONBOARD_MERCHANT.value:
            return {
                "merchant_id": payload.get("merchant_id"),
                "name": payload.get("merchant_name", payload.get("name", "Synthetic Merchant")),
                "mcc": payload.get("mcc", "5411"),
                "declared_mcc": payload.get("declared_mcc", payload.get("mcc", "5411")),
                "kyb_verified": payload.get("kyb_verified", True),
                "risk_score": payload.get("merchant_risk_score", payload.get("risk_score", 0.3)),
                "owner_customer_id": payload.get("customer_id"),
            }
        if action_type == ActionType.LINK_BENEFICIARY.value:
            return {
                "beneficiary_id": payload.get("beneficiary_id") or payload.get("beneficiary_account_id"),
                "customer_id": payload.get("customer_id"),
                "name": payload.get("beneficiary_name", "Payee"),
                "account_ref": payload.get("account_ref", f"ACC-{payload.get('beneficiary_id', 'ben')}"),
                "risk_score": payload.get("beneficiary_risk_score", 0.2),
            }
        if action_type == ActionType.OPEN_ACCOUNT.value:
            return {
                "account_id": payload.get("account_id"),
                "customer_id": payload.get("customer_id"),
                "balance": payload.get("balance", 50000),
            }
        if action_type == ActionType.SIMULATE_GENAI_CONTEXT.value:
            return {
                "attack_family": payload.get("attack_family"),
                "customer_id": payload.get("customer_id"),
                "capability_ids": payload.get("capability_ids") or [],
                "channels": payload.get("channels") or [],
                "genai_features": payload.get("genai_features") or {},
                "victim_coerced": payload.get("victim_coerced", False),
                "agent_mediated": payload.get("agent_mediated", False),
            }
        # Default: payment initiation
        return {
            "transaction_id": payload.get("transaction_id"),
            "customer_id": payload.get("customer_id"),
            "device_id": payload.get("device_id"),
            "amount": payload.get("amount", 0),
            "payment_rail": payload.get("payment_rail", "upi"),
            "authentication_method": payload.get("authentication_method", "otp"),
            "merchant_id": payload.get("merchant_id"),
            "merchant_risk_score": payload.get("merchant_risk_score", 0.3),
            "beneficiary_id": payload.get("beneficiary_id") or payload.get("beneficiary_account_id"),
            "account_id": payload.get("account_id"),
            "payment_path": payload.get("payment_path"),
            "entry_point": payload.get("entry_point"),
            "genai_features": payload.get("genai_features") or {},
            "capability_ids": payload.get("capability_ids") or [],
            "victim_coerced": payload.get("victim_coerced"),
            "attack_family": payload.get("attack_family"),
        }

    def _observation_to_response(self, obs: SandboxObservation) -> Dict[str, Any]:
        """Normalize SandboxObservation for Red Team agents."""
        legacy = obs.to_legacy_response()
        legacy["observation"] = obs.model_dump()
        legacy["control_triggers"] = obs.control_triggers
        legacy["action_type"] = obs.action_type
        legacy["state_snapshot"] = obs.state_snapshot
        # Hoist defense scores to top-level for FailureAnalyzer / tests
        legacy["risk_score"] = obs.risk_score
        legacy["ml_score"] = obs.ml_score
        legacy["rule_risk"] = obs.rule_risk
        legacy["anomaly_score"] = obs.anomaly_score
        return legacy

    def get_sandbox(self) -> PaymentSandbox:
        return self.sandbox

    def _sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure response is JSON/msgpack serializable for LangGraph checkpointing."""

        def _default(obj: Any) -> str:
            if isinstance(obj, datetime):
                return obj.isoformat()
            return str(obj)

        return json.loads(json.dumps(data, default=_default))
