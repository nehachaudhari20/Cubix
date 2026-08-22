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
    evasion_outcome: str = "unknown"  # bypassed | challenged | blocked
    analysis_outcome: Optional[str] = None
    blocking_control: Optional[str] = None
    attack_variant: Optional[str] = None
    control_triggers: List[str] = Field(default_factory=list)
    ml_score: Optional[float] = None
    rule_risk: Optional[float] = None
    risk_score: Optional[float] = None
    label: Optional[int] = None  # 1=fraud attempt, 0=legit
    features: Dict[str, Any] = Field(default_factory=dict)
    amount: Optional[float] = None
    step: Optional[int] = None
    source: str = "red_team"
    timestamp: str


class HardeningReport(BaseModel):
    """Before/after comparison for Loop B hardening."""
    v1_version: str = "v1"
    v2_version: str = "v2"
    buffer_records: int = 0
    v1_buffer_mean_score: float = 0.0
    v2_buffer_mean_score: float = 0.0
    buffer_score_lift: float = 0.0
    v1_baseline_fraud_recall: float = 0.0
    v2_baseline_fraud_recall: float = 0.0
    bypassed_attacks: int = 0
    recommend_swap: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)
