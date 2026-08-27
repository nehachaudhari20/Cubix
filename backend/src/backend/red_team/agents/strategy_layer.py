"""
Strategy Layer — mutate current composite before CVSS jump.
"""

from __future__ import annotations

import os
from typing import List, Optional, Set

from ..schemas import Hypothesis, StrategyDecision
from ..agent_helpers import OfflineKnowledge
from ..kb_campaign_builder import build_hypothesis_from_family
from ..deepteam.family_scorer import prioritize_families
from ..deepteam.schemas import AttackCandidate
from .memory_agent import MemoryAgent

_MUTATE_CHAIN = ("sequential", "tree", "crescendo", "linear")


def _mutate_budget() -> int:
    try:
        return max(0, int(os.environ.get("RED_TEAM_MUTATE_BEFORE_JUMP", "2")))
    except ValueError:
        return 2


class StrategyLayer:
    """Selects next campaign strategy: mutate current first, then CVSS jump."""

    def __init__(self, memory_agent: MemoryAgent):
        self.memory = memory_agent
        self.kb = OfflineKnowledge()

    def decide(
        self,
        current_hypothesis: Optional[Hypothesis] = None,
        last_analysis: Optional[dict] = None,
        iteration: int = 0,
        max_iterations: int = 5,
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
        successes = self.memory.get_memories_by_condition("outcome", "success")

        # --- Failure on current → mutate composite before CVSS jump ---
        if (
            current_hypothesis
            and last_analysis
            and last_analysis.get("outcome") == "failure"
        ):
            mutate_decision = self._try_mutate_current(current_hypothesis, last_analysis)
            if mutate_decision:
                return mutate_decision

            if ranked:
                mutations = last_analysis.get("mutation_suggestions") or []
                nxt = self._hypothesis_from_candidate(ranked[0])
                return StrategyDecision(
                    action="continue",
                    next_hypothesis=nxt,
                    reason=(
                        f"Mutate budget exhausted for {current_hypothesis.primary_family}; "
                        f"CVSS jump to {ranked[0].family_id} "
                        f"(score={ranked[0].cvss.composite}). "
                        f"Hint: {mutations[0] if mutations else 'adjust params'}"
                    ),
                    confidence=0.8,
                )

        if not ranked and not current_hypothesis:
            stats = self.kb.kb_stats()
            return StrategyDecision(
                action="stop",
                next_hypothesis=None,
                reason=(
                    f"All {stats['simulatable_families']} simulatable KB families exercised "
                    f"({stats['total_families']} total)"
                ),
                confidence=0.95,
            )

        if len(successes) >= 5:
            return StrategyDecision(
                action="stop",
                next_hypothesis=None,
                reason=f"Found {len(successes)} successful paths across KB families",
                confidence=0.9,
            )

        if ranked:
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

        return StrategyDecision(
            action="stop",
            next_hypothesis=None,
            reason="No remaining candidates",
            confidence=0.9,
        )

    def _try_mutate_current(
        self,
        current: Hypothesis,
        last_analysis: dict,
    ) -> Optional[StrategyDecision]:
        budget = _mutate_budget()
        if budget <= 0:
            return None

        attempts = self._mutation_attempts_for(current.primary_family)
        if attempts >= budget:
            return None

        mutated = self._build_mutated_hypothesis(current, last_analysis, attempts)
        hints = last_analysis.get("mutation_suggestions") or []
        return StrategyDecision(
            action="mutate",
            next_hypothesis=mutated,
            reason=(
                f"Mutate current {current.primary_family}"
                f"{('+' + str(current.composite_families)) if current.composite_families else ''} "
                f"(attempt {attempts + 1}/{budget}) after "
                f"{last_analysis.get('blocking_control', 'block')}. "
                f"Hint: {hints[0] if hints else 'vary amount/rail/timing'}"
            ),
            confidence=0.88,
        )

    def _mutation_attempts_for(self, primary_family: str) -> int:
        count = 0
        for m in self.memory.memories:
            conditions = m.applicable_conditions or {}
            if conditions.get("primary_family") != primary_family:
                continue
            strategy = (m.strategy_used or "") + " " + (conditions.get("strategy") or "")
            if "mutate" in strategy.lower() or conditions.get("mutation_attempt"):
                count += 1
        # Also count memories tagged via hypothesis jailbreak after mutate
        for m in self.memory.memories:
            conditions = m.applicable_conditions or {}
            if conditions.get("primary_family") == primary_family and conditions.get("is_mutation"):
                count += 1
        return count

    def _build_mutated_hypothesis(
        self,
        current: Hypothesis,
        last_analysis: dict,
        attempt: int,
    ) -> Hypothesis:
        next_strategy = _MUTATE_CHAIN[min(attempt, len(_MUTATE_CHAIN) - 1)]
        # Keep composites; force tree/crescendo/sequential for deeper exploration
        if current.composite_families and next_strategy == "linear":
            next_strategy = "sequential"

        hints = last_analysis.get("mutation_suggestions") or []
        risk = last_analysis.get("risk_score")
        reasoning = (
            f"{current.reasoning} [MUTATE#{attempt + 1}] "
            f"Prior block={last_analysis.get('blocking_control')} "
            f"risk={risk}. Apply: {'; '.join(hints[:3]) or 'vary amount/rail/GenAI'}."
        )
        return current.model_copy(
            update={
                "name": f"{current.name} [mutate-{next_strategy}]",
                "jailbreak_strategy": next_strategy,
                "novelty_score": min(0.95, (current.novelty_score or 0.6) + 0.05),
                "success_probability": max(0.15, (current.success_probability or 0.4) - 0.05),
                "reasoning": reasoning,
                "suggested_variant": current.suggested_variant or "mutated",
            }
        )

    def prioritized_candidates(self, tested_ids: Optional[Set[str]] = None) -> List[AttackCandidate]:
        tested = tested_ids or set(self._tested_family_ids())
        simulatable = self.kb.get_simulatable_families()
        return prioritize_families(
            simulatable,
            self.kb.signals,
            tested_ids=tested,
            memories=self.memory.memories,
            limit=15,
        )

    def _tested_family_ids(self) -> List[str]:
        tested: List[str] = []
        for m in self.memory.memories:
            conditions = m.applicable_conditions or {}
            # Mutated retries should NOT mark family as fully tested for CVSS skip
            if conditions.get("is_mutation"):
                continue
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
