"""
Strategy Layer
Decides the next attack based on memory and current state.
"""

from typing import Optional
from ..schemas import Hypothesis, StrategyDecision, MemoryEntry
from ..agents.memory_agent import MemoryAgent


class StrategyLayer:
    """
    Strategy Layer.
    Chooses the next action: continue, stop, or mutate.
    """
    
    def __init__(self, memory_agent: MemoryAgent):
        self.memory = memory_agent
    
    def decide(self, current_hypothesis: Optional[Hypothesis] = None) -> StrategyDecision:
        """
        Decide what to do next.
        INPUT: Current hypothesis (optional)
        OUTPUT: StrategyDecision
        """
        # 1. Check if we have successful strategies to retry
        successful = self.memory.get_successful_strategies()
        
        if successful:
            # Retry the best strategy with a mutation
            best = successful[0]
            return StrategyDecision(
                action="continue",
                next_hypothesis=None,  # Will use same hypothesis
                reason=f"Retrying successful strategy: {best.name} (success rate: {best.success_count}/{best.success_count + best.failure_count})",
                confidence=best.confidence
            )
        
        # 2. Check if we have enough memories to stop
        if len(self.memory.memories) > 10:
            return StrategyDecision(
                action="stop",
                next_hypothesis=None,
                reason=f"Reached {len(self.memory.memories)} memories. Time to harden the Blue Team.",
                confidence=0.9
            )
        
        # 3. Default: continue with current or new hypothesis
        return StrategyDecision(
            action="continue",
            next_hypothesis=current_hypothesis,
            reason="Continue exploring attack space",
            confidence=0.7
        )
    
    def should_stop(self) -> bool:
        """Check if we should stop attacking."""
        total_memories = len(self.memory.memories)
        if total_memories >= 10:
            return True
        # Check if we have enough failures to understand the system
        failures = [m for m in self.memory.memories if m.applicable_conditions.get("outcome") == "failure"]
        if len(failures) >= 5:
            return True
        return False