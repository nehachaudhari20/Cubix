"""
Red Team State Management
Tracks the state of attack campaigns and agent memory.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AttackStep:
    """A single step in an attack campaign."""
    step_id: str
    action: str
    payload: Dict[str, Any]
    expected_outcome: Optional[str] = None
    actual_outcome: Optional[str] = None
    sandbox_response: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AttackCampaign:
    """A complete attack campaign with multiple steps."""
    campaign_id: str
    hypothesis: str
    objective: str
    target_stage: str
    attack_family: str
    steps: List[AttackStep] = field(default_factory=list)
    status: str = "planning"  # planning, executing, completed, failed
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    success: bool = False
    summary: Optional[str] = None


@dataclass
class MemoryEntry:
    """A semantic memory entry from an experiment."""
    memory_id: str
    context: str
    observed_control: str
    response: str
    evidence_count: int = 1
    confidence: float = 0.5
    applicable_conditions: Dict[str, Any] = field(default_factory=dict)
    last_validated: str = field(default_factory=lambda: datetime.now().isoformat())
    strategy_used: Optional[str] = None


@dataclass
class StrategyMemory:
    """A stored strategy with success/failure metrics."""
    strategy_id: str
    name: str
    description: str
    conditions: Dict[str, Any]
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[str] = None
    confidence: float = 0.5


class RedTeamState:
    """Central state management for the Red Team."""
    
    def __init__(self):
        self.campaigns: Dict[str, AttackCampaign] = {}
        self.memories: List[MemoryEntry] = []
        self.strategies: List[StrategyMemory] = []
        self.current_campaign_id: Optional[str] = None
        self.experiment_count: int = 0
        self.successful_attacks: int = 0
        self.failed_attacks: int = 0
    
    def create_campaign(self, hypothesis: str, objective: str, target_stage: str, attack_family: str) -> str:
        """Create a new attack campaign."""
        campaign_id = f"camp_{len(self.campaigns) + 1:04d}"
        campaign = AttackCampaign(
            campaign_id=campaign_id,
            hypothesis=hypothesis,
            objective=objective,
            target_stage=target_stage,
            attack_family=attack_family
        )
        self.campaigns[campaign_id] = campaign
        self.current_campaign_id = campaign_id
        return campaign_id
    
    def add_memory(self, context: str, observed_control: str, response: str, 
                   applicable_conditions: Dict[str, Any], strategy_used: Optional[str] = None) -> str:
        """Add a new semantic memory entry."""
        memory_id = f"mem_{len(self.memories) + 1:04d}"
        entry = MemoryEntry(
            memory_id=memory_id,
            context=context,
            observed_control=observed_control,
            response=response,
            applicable_conditions=applicable_conditions,
            strategy_used=strategy_used
        )
        self.memories.append(entry)
        return memory_id
    
    def add_strategy(self, name: str, description: str, conditions: Dict[str, Any]) -> str:
        """Add a new strategy."""
        strategy_id = f"strat_{len(self.strategies) + 1:04d}"
        strategy = StrategyMemory(
            strategy_id=strategy_id,
            name=name,
            description=description,
            conditions=conditions
        )
        self.strategies.append(strategy)
        return strategy_id
    
    def get_memories_by_condition(self, condition: str, value: Any) -> List[MemoryEntry]:
        """Get memories that match a specific condition."""
        return [
            m for m in self.memories
            if m.applicable_conditions.get(condition) == value
        ]
    
    def get_strategies_by_condition(self, condition: str, value: Any) -> List[StrategyMemory]:
        """Get strategies that match a specific condition."""
        return [
            s for s in self.strategies
            if s.conditions.get(condition) == value
        ]
    
    def get_best_strategy(self, context: Dict[str, Any]) -> Optional[StrategyMemory]:
        """Get the best strategy for a given context."""
        best = None
        best_score = -1
        
        for strategy in self.strategies:
            # Check if strategy matches context
            matches = True
            for key, value in context.items():
                if key in strategy.conditions and strategy.conditions[key] != value:
                    matches = False
                    break
            
            if matches:
                # Score based on success rate and confidence
                total = strategy.success_count + strategy.failure_count
                if total > 0:
                    score = (strategy.success_count / total) * strategy.confidence
                    if score > best_score:
                        best_score = score
                        best = strategy
        
        return best
    
    def update_strategy_result(self, strategy_id: str, success: bool):
        """Update a strategy's success/failure count."""
        for strategy in self.strategies:
            if strategy.strategy_id == strategy_id:
                if success:
                    strategy.success_count += 1
                else:
                    strategy.failure_count += 1
                break
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Red Team statistics."""
        return {
            "total_campaigns": len(self.campaigns),
            "experiment_count": self.experiment_count,
            "successful_attacks": self.successful_attacks,
            "failed_attacks": self.failed_attacks,
            "memory_entries": len(self.memories),
            "strategies": len(self.strategies)
        }