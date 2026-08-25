"""Shared schemas for DeepTeam-inspired Red Team algorithms (Phase 1)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JailbreakStrategy(str, Enum):
    """Multi-turn attack strategies adapted from DeepTeam."""

    LINEAR = "linear"
    TREE = "tree"
    CRESCENDO = "crescendo"
    SEQUENTIAL = "sequential"


class CVSSScore(BaseModel):
    """Payment-fraud analogue of CVSS prioritization."""

    impact: float = Field(ge=0, le=10, description="Potential fraud amount scaled 0-10")
    exploitability: float = Field(ge=0, le=10, description="Ease of execution (fewer steps = higher)")
    exposure: float = Field(ge=0, le=10, description="Estimated control bypass probability x 10")
    composite: float = Field(ge=0, le=10, description="(impact*0.6)+(exploitability*0.3)+(exposure*0.1)")

    @classmethod
    def compute(
        cls,
        *,
        potential_amount: float,
        step_count: int,
        bypass_probability: float,
    ) -> "CVSSScore":
        impact = min(potential_amount / 10_000.0, 10.0)
        exploitability = max(0.0, 10.0 - (step_count * 0.5))
        exposure = min(max(bypass_probability, 0.0), 1.0) * 10.0
        composite = (impact * 0.6) + (exploitability * 0.3) + (exposure * 0.1)
        return cls(
            impact=round(impact, 3),
            exploitability=round(exploitability, 3),
            exposure=round(exposure, 3),
            composite=round(composite, 3),
        )


class MutationPayload(BaseModel):
    """Attacker-controlled field mutations applied to a legitimate baseline."""

    amount: Optional[float] = None
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    beneficiary_id: Optional[str] = None
    device_id: Optional[str] = None
    payment_rail: Optional[str] = None
    trust_score: Optional[float] = Field(default=None, ge=0, le=1)
    extra: Dict[str, Any] = Field(default_factory=dict)


class ValidatedVariation(BaseModel):
    """One sandbox-ready payload variation after Transform/Vary/Validate."""

    variation_id: str
    label: str
    action_payload: Dict[str, Any]
    validation_status: str = Field(description="VALID or INVALID")
    validation_reason: Optional[str] = None


class VariationSet(BaseModel):
    """Output of AttackEngine transform/vary/validate."""

    source_mutation: MutationPayload
    variations: List[ValidatedVariation] = Field(default_factory=list)
    valid_count: int = 0


class AttackCandidate(BaseModel):
    """Scored attack ready for StrategyLayer prioritization."""

    family_id: str
    family_name: str
    strategy: JailbreakStrategy
    cvss: CVSSScore
    plan_objective: str
    estimated_amount: float = 0.0
    step_count: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FraudJudgeVerdict(BaseModel):
    """BadLikert-style fraud investigator output for Control Gap Lab."""

    outcome: str
    expected_control_ids: List[str] = Field(default_factory=list)
    triggered_control_ids: List[str] = Field(default_factory=list)
    missing_control_ids: List[str] = Field(default_factory=list)
    investigator_summary: str
    control_gap_detected: bool = False
    remediation_hints: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0, le=1)
