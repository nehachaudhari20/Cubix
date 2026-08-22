"""
Strategy Layer — decides whether to continue, mutate, or stop based on memory.
Uses dynamic KB family queue instead of static templates.
"""

from typing import List, Optional

from ..schemas import Hypothesis, StrategyDecision
from ..agent_helpers import OfflineKnowledge
from ..kb_campaign_builder import build_hypothesis_from_family
from .memory_agent import MemoryAgent


class StrategyLayer:
    """Selects next campaign strategy from experiment memory and KB coverage."""

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

        tested = self._tested_family_ids()
        remaining = self.kb.get_untested_families(tested, limit=1)

        failures = self.memory.get_memories_by_condition("outcome", "failure")
        successes = self.memory.get_memories_by_condition("outcome", "success")

        if last_analysis and last_analysis.get("outcome") == "failure" and remaining:
            mutations = last_analysis.get("mutation_suggestions") or []
            blocking = last_analysis.get("blocking_control", "unknown")
            return StrategyDecision(
                action="continue",
                next_hypothesis=self._next_hypothesis(tested),
                reason=f"Next KB family after {blocking} block. Mutation hint: {mutations[0] if mutations else 'adjust params'}",
                confidence=0.8,
            )

        if not remaining:
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

        return StrategyDecision(
            action="continue",
            next_hypothesis=self._next_hypothesis(tested),
            reason=f"Continue KB exploration ({len(tested)} tested, {len(remaining)} remaining in queue)",
            confidence=0.75,
        )

    def _tested_family_ids(self) -> List[str]:
        return [
            m.applicable_conditions.get("primary_family")
            for m in self.memory.memories
            if m.applicable_conditions.get("primary_family")
        ]

    def _next_hypothesis(self, tested: List[str]) -> Optional[Hypothesis]:
        family = self.kb.get_untested_families(tested, limit=1)
        if family:
            return build_hypothesis_from_family(family[0])
        return None

    def coverage_report(self) -> dict:
        tested = set(self._tested_family_ids())
        simulatable = self.kb.get_simulatable_families()
        return {
            "tested": len(tested),
            "simulatable": len(simulatable),
            "remaining": len([f for f in simulatable if f.get("attack_id") not in tested]),
            "kb_stats": self.kb.kb_stats(),
        }
