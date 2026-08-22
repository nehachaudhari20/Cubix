"""
Sandbox action and observation contracts.

Every action executed by the Orchestrator returns a SandboxObservation
that Red Team and Blue Team consume as shared experiment evidence.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Executable Red Team / Sandbox action types."""

    REGISTER_CUSTOMER = "register_customer"
    REGISTER_DEVICE = "register_device"
    VERIFY_KYC = "verify_kyc"
    AUTHENTICATE = "authenticate"
    INITIATE_PAYMENT = "initiate_payment"


class JourneyStep(BaseModel):
    step: str
    result: Dict[str, Any]


class SandboxObservation(BaseModel):
    """Structured result returned after any Sandbox action executes."""

    action_id: str
    action_type: str
    decision: str  # ALLOW | CHALLENGE | BLOCK | PASS | FAIL
    reason: str
    message: str = ""
    risk_score: Optional[float] = None
    control_triggers: List[str] = Field(default_factory=list)
    journey: List[JourneyStep] = Field(default_factory=list)
    state_snapshot: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str

    # Payment-specific (initiate_payment)
    transaction_id: Optional[str] = None
    ml_score: Optional[float] = None
    rule_risk: Optional[float] = None
    settled: bool = False
    settlement_detail: Optional[Dict[str, Any]] = None

    def to_legacy_response(self) -> Dict[str, Any]:
        """Backward-compatible dict for existing callers (process_transaction)."""
        return {
            "transaction_id": self.transaction_id or self.action_id,
            "decision": self.decision,
            "reason": self.reason,
            "message": self.message or f"Transaction {self.decision.lower()}ed: {self.reason}",
            "journey": [step.model_dump() for step in self.journey],
            "state": {
                "risk_score": self.risk_score,
                "ml_score": self.ml_score,
                "rule_risk": self.rule_risk,
                "settled": self.settled,
                "settlement_detail": self.settlement_detail,
                "control_triggers": self.control_triggers,
            },
            "timestamp": self.timestamp,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "state_snapshot": self.state_snapshot,
        }
