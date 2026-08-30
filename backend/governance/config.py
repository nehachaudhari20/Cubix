"""Risk policy configuration — blend weights, thresholds, governance metadata."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RiskBlendWeights(BaseModel):
    rule_risk: float = 0.40
    ml_score: float = 0.45
    anomaly_score: float = 0.15
    total_weight_required: float = 1.00

    def normalized(self) -> "RiskBlendWeights":
        total = self.rule_risk + self.ml_score + self.anomaly_score
        if total <= 0:
            total = 1.0
        return RiskBlendWeights(
            rule_risk=round(self.rule_risk / total, 4),
            ml_score=round(self.ml_score / total, 4),
            anomaly_score=round(self.anomaly_score / total, 4),
        )


class PolicyThresholds(BaseModel):
    allow_max: float = 0.40
    challenge_min: float = 0.40
    challenge_max: float = 0.70
    block_min: float = 0.70


class HardBlockRule(BaseModel):
    rule_id: str
    description: str
    enabled: bool = True


class RiskPolicy(BaseModel):
    version: str = "policy_v1_2"
    blend: RiskBlendWeights = Field(default_factory=RiskBlendWeights)
    thresholds: PolicyThresholds = Field(default_factory=PolicyThresholds)
    hard_block_rules: List[HardBlockRule] = Field(default_factory=lambda: [
        HardBlockRule(rule_id="intent_amount_exceeded", description="Amount exceeds authorized cap"),
        HardBlockRule(rule_id="invalid_agent_identity", description="Agent identity not verified"),
        HardBlockRule(rule_id="known_synthetic_mule", description="Destination is known mule account"),
    ])
    calibration_method: str = "cost_matrix"
    governance_notes: str = "Prototype configuration. Thresholds selected for balanced FPR/recall."

    def decide(self, risk_score: float) -> str:
        if risk_score >= self.thresholds.block_min:
            return "BLOCK"
        elif risk_score >= self.thresholds.challenge_min:
            return "CHALLENGE"
        return "ALLOW"


class ExperimentProvenance(BaseModel):
    experiment_id: str
    simulation_run_id: str
    model_version: str
    policy_version: str
    attack_family: str
    scenario_id: str
    outcome: str
    observed_controls: List[str]
    root_cause_category: Optional[str] = None
    recommended_feature_pack: Optional[str] = None
    data_scope: str = "SYNTHETIC_ONLY"
    created_at: str


@lru_cache
def get_risk_policy() -> RiskPolicy:
    return RiskPolicy()
