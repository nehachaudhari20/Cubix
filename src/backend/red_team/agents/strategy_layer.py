"""
Strategy Layer — CVSS-prioritized family selection with experiment memory.
"""

from __future__ import annotations

from typing import List, Optional, Set

from ..schemas import Hypothesis, StrategyDecision
from ..agent_helpers import OfflineKnowledge
from ..kb_campaign_builder import build_hypothesis_from_family
from ..deepteam.family_scorer import prioritize_families
from ..deepteam.schemas import AttackCandidate
from .memory_agent import MemoryAgent


class StrategyLayer:
    """Selects next campaign strategy from CVSS-ranked KB families + memory."""

    def __init__(self, memory_agent: MemoryAgent):
        self.memory = memory_agent
        self.kb = OfflineKnowledge()

    def decide(
        self,
        current_hypothesis: Optional[Hypothesis] = None,
        last_analysis: Optional[dict] = None,
        iteration: int = 0,
        max_iterations: int = 3,
    ) -> StrategyDecision:
        if iteration >= max_iterations:
            return StrategyDecision(
                action="stop",
                next_hypothesis=None,
                reason=f"Reached max iterations ({max_iterations})",
                confidence=0.95,
            )

        tested = set(self._tested_family_ids())
        ranked = self.prioritized_candidates(tested)
        failures = self.memory.get_memories_by_condition("outcome", "failure")
        successes = self.memory.get_memories_by_condition("outcome", "success")

        if last_analysis and last_analysis.get("outcome") == "failure" and ranked:
            mutations = last_analysis.get("mutation_suggestions") or []
            blocking = last_analysis.get("blocking_control", "unknown")
            nxt = self._hypothesis_from_candidate(ranked[0])
            return StrategyDecision(
                action="continue",
                next_hypothesis=nxt,
                reason=(
                    f"CVSS next {ranked[0].family_id} (score={ranked[0].cvss.composite}) "
                    f"after {blocking} block. Hint: {mutations[0] if mutations else 'adjust params'}"
                ),
                confidence=0.85,
            )

        if not ranked:
            stats = self.kb.kb_stats()
            return StrategyDecision(
                action="stop",
                next_hypothesis=None,
                reason=(
                    f"All {stats['simulatable_families']} simulatable KB families exercised "
                    f"({stats['total_families']} total, {stats['total_signals']} signals, "
                    f"{stats['total_stages']} stages)"
                ),
                confidence=0.95,
            )

        if len(successes) >= 3:
            return StrategyDecision(
                action="stop",
                next_hypothesis=None,
                reason=f"Found {len(successes)} successful paths across KB families",
                confidence=0.9,
            )

        top = ranked[0]
        return StrategyDecision(
            action="continue",
            next_hypothesis=self._hypothesis_from_candidate(top),
            reason=(
                f"CVSS prioritize {top.family_id} "
                f"(composite={top.cvss.composite}, impact={top.cvss.impact}, "
                f"exploitability={top.cvss.exploitability}, exposure={top.cvss.exposure})"
            ),
            confidence=min(0.95, 0.6 + top.cvss.composite / 20.0),
        )

    def prioritized_candidates(self, tested_ids: Optional[Set[str]] = None) -> List[AttackCandidate]:
        tested = tested_ids or set(self._tested_family_ids())
        simulatable = self.kb.get_simulatable_families()
        return prioritize_families(
            simulatable,
            self.kb.signals,
            tested_ids=tested,
            memories=self.memory.memories,
            limit=10,
        )

    def _tested_family_ids(self) -> List[str]:
        tested: List[str] = []
        for m in self.memory.memories:
            conditions = m.applicable_conditions or {}
            if conditions.get("primary_family"):
                tested.append(conditions["primary_family"])
            tested.extend(fid for fid in (conditions.get("composite_families") or []) if fid)
            tested.extend(fid for fid in (conditions.get("covered_families") or []) if fid)
        return list(dict.fromkeys(tested))

    def _hypothesis_from_candidate(self, candidate: AttackCandidate) -> Optional[Hypothesis]:
        family = self.kb.get_family(candidate.family_id)
        if not family:
            return None
        hypothesis = build_hypothesis_from_family(family)
        hypothesis.success_probability = min(0.95, candidate.cvss.exposure / 10.0)
        hypothesis.reasoning = (
            f"{hypothesis.reasoning} CVSS composite={candidate.cvss.composite}."
        )
        return hypothesis

    def coverage_report(self) -> dict:
        tested = set(self._tested_family_ids())
        simulatable = self.kb.get_simulatable_families()
        ranked = self.prioritized_candidates(tested)
        return {
            "tested": len(tested),
            "simulatable": len(simulatable),
            "remaining": len([f for f in simulatable if f.get("attack_id") not in tested]),
            "kb_stats": self.kb.kb_stats(),
            "cvss_top5": [
                {
                    "family_id": item.family_id,
                    "composite": item.cvss.composite,
                    "amount": item.estimated_amount,
                }
                for item in ranked[:5]
            ],
        }
