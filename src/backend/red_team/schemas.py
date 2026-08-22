"""
Red Team Pydantic Schemas
Defines all data contracts between agents in the pipeline.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# ============================================================
# THREAT HUNTER OUTPUT
# ============================================================

class Hypothesis(BaseModel):
    """A single attack hypothesis discovered by the Threat Hunter."""
    name: str = Field(description="Descriptive name of the attack")
    primary_family: str = Field(description="Primary attack family ID (e.g., SIF-001)")
    composite_families: List[str] = Field(default_factory=list, description="Additional family IDs if composite")
    target_stages: List[str] = Field(description="Targeted lifecycle stages")
    novelty_score: float = Field(ge=0, le=1, description="Novelty score (0-1)")
    success_probability: float = Field(ge=0, le=1, description="Estimated success probability (0-1)")
    prerequisites: List[str] = Field(description="Required conditions for this attack")
    attack_flow_summary: str = Field(description="Brief step-by-step summary")
    reasoning: str = Field(description="Chain-of-thought reasoning")
    suggested_variant: Optional[str] = Field(default=None, description="Specific variant to use")

class ThreatHunterOutput(BaseModel):
    """Full output from Threat Hunter."""
    hypotheses: List[Hypothesis] = Field(description="List of discovered hypotheses")
    confidence: float = Field(ge=0, le=1, description="Overall confidence")


# ============================================================
# ATTACK PLANNER INPUT & OUTPUT
# ============================================================

class PlanStep(BaseModel):
    """A single step in an attack campaign."""
    step: int = Field(description="Step number")
    action_type: str = Field(default="initiate_payment", description="Sandbox action type")
    action: str = Field(description="Action description")
    target_control: str = Field(description="Control being targeted")
    payload_template: Dict[str, Any] = Field(default_factory=dict, description="Template values for payload")
    expected_outcome: str = Field(description="Expected outcome: PASS, ALLOW, FLAG, BLOCK")
    rationale: str = Field(description="Why this step is necessary")

class AttackPlan(BaseModel):
    """Complete attack plan from Planner."""
    campaign_name: str = Field(description="Campaign name")
    objective: str = Field(description="Campaign objective")
    target_stages: List[str] = Field(description="Targeted lifecycle stages")
    primary_family: str = Field(description="Primary attack family")
    selected_variant: str = Field(description="Selected variant")
    steps: List[PlanStep] = Field(description="Attack steps")
    success_criteria: str = Field(description="Success criteria")
    estimated_complexity: str = Field(description="low, medium, high")
    reasoning: str = Field(description="Chain-of-thought reasoning")


# ============================================================
# ATTACK GENERATOR OUTPUT
# ============================================================

class ActionPayload(BaseModel):
    """Executable sandbox action in a Red Team campaign."""
    action_type: str
    action_payload: Dict[str, Any]
    step: int
    total_steps: int
    is_final: bool
    campaign_id: str
    attack_family: str
    attack_variant: str = "default"
    target_control: str
    expected_outcome: str = "PASS"
    narrative: Optional[str] = None


class Payload(BaseModel):
    """Legacy payment payload (kept for compatibility)."""
    transaction_id: str
    timestamp: str
    customer_id: str
    device_id: str
    amount: float
    currency: str = "INR"
    payment_rail: str
    transaction_type: str
    authentication_method: str
    merchant_id: Optional[str] = None
    merchant_risk_score: float
    is_new_device: bool
    is_new_beneficiary: bool
    beneficiary_account_id: Optional[str] = None
    narrative: Optional[str] = None
    step: int
    total_steps: int
    is_final: bool
    campaign_id: str
    attack_family: str
    attack_variant: str
    target_control: str
    expected_outcome: str
    action_type: str = "initiate_payment"
    action_payload: Optional[Dict[str, Any]] = None

class GeneratedSequence(BaseModel):
    """Full sequence of actions for a campaign."""
    campaign_id: str
    payloads: List[ActionPayload]
    total_payloads: int


# ============================================================
# FAILURE ANALYZER OUTPUT
# ============================================================

class AnalysisResult(BaseModel):
    """Analysis of a Sandbox response."""
    outcome: str = Field(description="success or failure")
    blocking_control: Optional[str] = Field(description="Which control blocked the attack")
    blocking_reason: Optional[str] = Field(description="Why it was blocked")
    risk_score: Optional[float] = Field(description="Risk score at decision point")
    learnings: List[str] = Field(description="Key learnings for future attacks")
    mutation_suggestions: List[str] = Field(description="How to mutate this attack")
    confidence: float = Field(ge=0, le=1, description="Confidence in analysis")
    journey_trace: List[Dict[str, Any]] = Field(default_factory=list, description="Full journey trace from Sandbox")


# ============================================================
# MEMORY AGENT OUTPUT
# ============================================================

class MemoryEntry(BaseModel):
    """A semantic memory entry."""
    memory_id: str
    context: str
    observed_control: str
    response: str
    attack_attempted: str
    evidence_count: int = 1
    confidence: float = 0.5
    applicable_conditions: Dict[str, Any] = Field(default_factory=dict)
    strategy_used: Optional[str] = None
    last_validated: str

class StrategyMemory(BaseModel):
    """A stored strategy with success metrics."""
    strategy_id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.5


# ============================================================
# STRATEGY LAYER OUTPUT
# ============================================================

class StrategyDecision(BaseModel):
    """Decision from the Strategy Layer."""
    action: str = Field(description="continue, stop, mutate")
    next_hypothesis: Optional[Hypothesis] = Field(description="Next hypothesis to pursue")
    reason: str = Field(description="Reasoning for this decision")
    confidence: float = Field(ge=0, le=1)