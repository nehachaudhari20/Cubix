"""CVSS-style attack prioritization (DeepTeam-inspired). Phase 2+ implementation."""

from __future__ import annotations

from typing import List

from .schemas import AttackCandidate, CVSSScore, JailbreakStrategy


def prioritize_attacks(candidates: List[AttackCandidate]) -> List[AttackCandidate]:
    """Sort attack candidates by composite CVSS score descending."""
    return sorted(candidates, key=lambda item: item.cvss.composite, reverse=True)


def score_family(
    family_id: str,
    family_name: str,
    *,
    potential_amount: float,
    step_count: int,
    bypass_probability: float,
    strategy: JailbreakStrategy = JailbreakStrategy.LINEAR,
    plan_objective: str = "",
) -> AttackCandidate:
    cvss = CVSSScore.compute(
        potential_amount=potential_amount,
        step_count=step_count,
        bypass_probability=bypass_probability,
    )
    return AttackCandidate(
        family_id=family_id,
        family_name=family_name,
        strategy=strategy,
        cvss=cvss,
        plan_objective=plan_objective,
        estimated_amount=potential_amount,
        step_count=step_count,
    )
