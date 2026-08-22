"""Blue Team data contracts."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FraudShieldPrediction(BaseModel):
    """ML fraud score for one transaction."""
    fraud_probability: float = Field(ge=0, le=1)
    decision_threshold: float = Field(default=0.5)
    is_fraud_predicted: bool = False
    model_version: str = "v1"
    features_used: List[str] = Field(default_factory=list)
    missing_features: List[str] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    """One sandbox observation stored for Loop B hardening."""
    evidence_id: str
    campaign_id: str
    attack_family: str
    action_type: str
    sandbox_decision: str
    control_triggers: List[str] = Field(default_factory=list)
    ml_score: Optional[float] = None
    rule_risk: Optional[float] = None
    risk_score: Optional[float] = None
    label: Optional[int] = None  # 1=fraud attempt, 0=legit
    features: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str
