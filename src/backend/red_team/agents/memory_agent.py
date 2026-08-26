"""
Memory Agent
Stores and retrieves semantic memories from experiments.
Uses ChromaDB for vector search (optional) and in-memory store for MVP.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from ..schemas import AnalysisResult, MemoryEntry, StrategyMemory, Hypothesis


class MemoryAgent:
    """
    Memory Agent.
    Stores environment-specific observations and strategies.
    """
    
    def __init__(self, use_vector_db: bool = False):
        self.memories: List[MemoryEntry] = []
        self.strategies: List[StrategyMemory] = []
        self.use_vector_db = use_vector_db
        
        # Initialize ChromaDB if needed
        if use_vector_db:
            try:
                import chromadb
                self.client = chromadb.Client()
                self.collection = self.client.create_collection("attack_memories")
            except Exception as e:
                print(f"⚠️ ChromaDB init failed: {e}")
                self.use_vector_db = False
    
    def store_analysis(self, analysis: AnalysisResult, hypothesis: Hypothesis, context: Dict[str, Any]) -> MemoryEntry:
        """
        Store an analysis result as a memory entry.
        """
        memory = MemoryEntry(
            memory_id=f"mem_{uuid.uuid4().hex[:8]}",
            context=f"Attack: {hypothesis.name} | Outcome: {analysis.outcome} | Control: {analysis.blocking_control}",
            observed_control=analysis.blocking_control or "None",
            response=analysis.outcome,
            attack_attempted=hypothesis.name,
            evidence_count=1,
            confidence=analysis.confidence,
            applicable_conditions={
                "primary_family": hypothesis.primary_family,
                "composite_families": list(hypothesis.composite_families or []),
                "covered_families": [hypothesis.primary_family, *(hypothesis.composite_families or [])],
                "target_stages": hypothesis.target_stages,
                "outcome": analysis.outcome,
                "blocking_control": analysis.blocking_control,
            },
            strategy_used=None,
            last_validated=datetime.now().isoformat()
        )
        
        self.memories.append(memory)
        
        # Store in vector DB if enabled
        if self.use_vector_db:
            try:
                self.collection.add(
                    documents=[memory.context],
                    metadatas=[{
                        "memory_id": memory.memory_id,
                        "outcome": analysis.outcome,
                        "blocking_control": analysis.blocking_control,
                        "attack_attempted": hypothesis.name
                    }],
                    ids=[memory.memory_id]
                )
            except Exception:
                pass
        
        return memory
    
    def store_strategy(self, name: str, description: str, conditions: Dict[str, Any]) -> StrategyMemory:
        """Store a successful strategy."""
        strategy = StrategyMemory(
            strategy_id=f"strat_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            conditions=conditions,
            success_count=0,
            failure_count=0,
            confidence=0.5
        )
        self.strategies.append(strategy)
        return strategy
    
    def get_memories_by_condition(self, condition: str, value: Any) -> List[MemoryEntry]:
        """Get memories that match a specific condition."""
        return [
            m for m in self.memories
            if m.applicable_conditions.get(condition) == value
        ]
    
    def get_successful_strategies(self) -> List[StrategyMemory]:
        """Get strategies with success rate > 0.6."""
        result = []
        for s in self.strategies:
            total = s.success_count + s.failure_count
            if total > 0 and (s.success_count / total) > 0.6:
                result.append(s)
        return result
    
    def get_memory_context(self) -> str:
        """Get a summary of memories for the Threat Hunter."""
        if not self.memories:
            return "No memories yet. Environment is untested."
        
        lines = ["Recent memory entries:"]
        for mem in self.memories[-5:]:
            lines.append(f"- {mem.context} (confidence: {mem.confidence})")
        return "\n".join(lines)
    
    def update_strategy_result(self, strategy_id: str, success: bool):
        """Update a strategy's success/failure count."""
        for strategy in self.strategies:
            if strategy.strategy_id == strategy_id:
                if success:
                    strategy.success_count += 1
                else:
                    strategy.failure_count += 1
                strategy.confidence = min(1.0, strategy.confidence + 0.05 if success else max(0.1, strategy.confidence - 0.05))
                break
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return {
            "total_memories": len(self.memories),
            "total_strategies": len(self.strategies),
            "successful_strategies": len(self.get_successful_strategies())
        }