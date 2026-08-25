"""
GenAI Context Engine — backward-compatible facade over KB-driven GenAIEngine.

Used by orchestrator action `simulate_genai_context` and risk blending.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .genai_engine import GenAIEngine, EngineResult


class GenAIContextEngine:
    """Facade that delegates to GenAIEngine and returns legacy dict shape."""

    def __init__(self, kb_path: Optional[str] = None):
        from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader
        self._engine = GenAIEngine(CanonicalKnowledgeLoader(kb_path) if kb_path else None)

    def evaluate(self, payload: Dict[str, Any], sandbox_state: Optional[Any] = None) -> Dict[str, Any]:
        family_id = payload.get("attack_family") or payload.get("family_id") or ""
        variant_id = payload.get("variant_id")
        result: EngineResult = self._engine.evaluate(
            attack_family_id=family_id,
            variant_id=variant_id,
            payload=payload,
            sandbox_state=sandbox_state,
        )
        return {
            "status": result.status,
            "genai_features": result.genai_features,
            "genai_risk_contribution": result.risk_contribution,
            "triggered_rules": result.triggered_rules,
            "evidence": result.evidence,
            "channels": result.evidence.get("channels") or [],
            "capability_ids": result.evidence.get("capability_ids") or [],
        }
