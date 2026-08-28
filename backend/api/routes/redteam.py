"""Red Team Chat — RAG-powered attack designer with KB context."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.knowledge.loader import KnowledgeLoader
from backend.llm.provider import get_llm, invoke_text
from backend.rag.rag_service import retrieve_for_attack, format_rag_context, rebuild_index

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/redteam", tags=["Red Team Chat"])

# Pre-load KB at module level
_kb: Optional[KnowledgeLoader] = None


def _get_kb() -> KnowledgeLoader:
    global _kb
    if _kb is None:
        _kb = KnowledgeLoader()
    return _kb


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ProposeRequest(BaseModel):
    prompt: str
    focus_family: Optional[str] = None  # e.g. "AML-001" to focus on a specific family
    max_context_families: int = 5


class AttackProposal(BaseModel):
    attack_name: str
    attack_family: Optional[str] = None
    target_surface: str
    lifecycle_stage: str
    description: str
    attack_flow: List[str]
    payloads: List[Dict[str, Any]]
    detection_signals: List[Dict[str, Any]]
    controls_targeted: List[str]
    novelty_notes: str
    kb_references: List[str]


class ProposeResponse(BaseModel):
    proposal: AttackProposal
    raw_llm_output: str
    context_families_used: List[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_rag_context(prompt: str, focus_family: Optional[str]) -> tuple[str, List[str]]:
    """Use RAG to retrieve the most relevant KB context for the prompt.
    Returns (context_string, list_of_family_ids_used)."""
    ctx = retrieve_for_attack(prompt, focus_family=focus_family)
    context_text = format_rag_context(ctx, max_families=5, max_vectors=3)
    families_used = [f.get("attack_id", "") for f in ctx["families"][:5]]
    vectors_used = [v.get("vector_id", "") for v in ctx["vectors"][:3]]
    return context_text, families_used + vectors_used


SYSTEM_PROMPT = """You are an expert Red Team attack designer for payment fraud detection systems.

Your role is to design novel, creative adversarial attacks against payment fraud detection systems. You have access to a knowledge base of known attack families, their tactics, and detection mechanisms.

When the user asks you to create an attack:
1. Design a NOVEL attack that does NOT simply copy an existing family
2. Combine techniques from multiple families when possible
3. Focus on EVADE detection — the goal is to find gaps in fraud controls
4. Be specific about payloads, amounts, timing, and evasion techniques
5. Consider which controls the attack would bypass and why

You MUST respond with a JSON object matching this exact structure:
{
  "attack_name": "short descriptive name",
  "attack_family": "NEW or existing family ID if extending",
  "target_surface": "payment|agent|network|auth_se|device|kyc|open_banking",
  "lifecycle_stage": "relevant lifecycle stage",
  "description": "2-3 sentence summary of the attack",
  "attack_flow": ["step 1", "step 2", ...],
  "payloads": [{"type": "payload type", "description": "what it does", "amount": "typical amount range", "evasion": "how it evades detection"}],
  "detection_signals": [{"name": "signal name", "detection_method": "how it might be detected"}],
  "controls_targeted": ["control 1", "control 2"],
  "novelty_notes": "what makes this attack novel compared to existing families",
  "kb_references": ["existing family IDs this draws inspiration from"]
}

Also include a brief natural-language explanation BEFORE the JSON block explaining your reasoning.
"""


@router.post("/propose")
async def propose_attack(req: ProposeRequest):
    """Generate a novel attack proposal using LLM + KB context."""
    llm = get_llm(temperature=0.7)
    if llm is None:
        raise HTTPException(
            status_code=503,
            detail="LLM not available. Set OPENROUTER_API_KEY (or another provider key) and RED_TEAM_USE_LLM=true in .env",
        )

    kb_context, context_families = _build_rag_context(req.prompt, req.focus_family)

    user_prompt = f"""Here is the knowledge base context of known attack families:

{kb_context}

---

User request: {req.prompt}

Design a novel attack based on this request. Respond with your reasoning followed by the JSON proposal."""

    raw = invoke_text(llm, SYSTEM_PROMPT, user_prompt)
    if raw is None:
        raise HTTPException(status_code=502, detail="LLM returned empty response")

    # Parse JSON from the response (may be wrapped in markdown code block)
    proposal = _parse_proposal(raw)

    return ProposeResponse(
        proposal=proposal,
        raw_llm_output=raw,
        context_families_used=context_families,
    )


def _parse_proposal(raw: str) -> AttackProposal:
    """Extract JSON AttackProposal from LLM output."""
    # Try to find JSON block in the response
    text = raw.strip()

    # Handle markdown code blocks
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()
    else:
        # Try to find JSON object in the text
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            text = text[brace_start : brace_end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # If JSON parsing fails, create a basic proposal from the raw text
        return AttackProposal(
            attack_name="LLM Generated Attack",
            target_surface="payment",
            lifecycle_stage="unknown",
            description=raw[:500],
            attack_flow=[],
            payloads=[],
            detection_signals=[],
            controls_targeted=[],
            novelty_notes="Could not parse structured output",
            kb_references=[],
        )

    return AttackProposal(
        attack_name=data.get("attack_name", "Untitled Attack"),
        attack_family=data.get("attack_family"),
        target_surface=data.get("target_surface", "payment"),
        lifecycle_stage=data.get("lifecycle_stage", "unknown"),
        description=data.get("description", ""),
        attack_flow=data.get("attack_flow", []),
        payloads=data.get("payloads", []),
        detection_signals=data.get("detection_signals", []),
        controls_targeted=data.get("controls_targeted", []),
        novelty_notes=data.get("novelty_notes", ""),
        kb_references=data.get("kb_references", []),
    )


@router.get("/families")
async def list_families():
    """List all KB families for the chat sidebar."""
    kb = _get_kb()
    return [
        {
            "attack_id": f.get("attack_id"),
            "name": f.get("name"),
            "lifecycle_stage": f.get("lifecycle_stage"),
            "simulation_type": f.get("simulation_type"),
            "surface": f.get("surface"),
        }
        for f in kb.families
    ]


@router.post("/rag/rebuild")
async def rebuild_rag_index():
    """Force rebuild the ChromaDB RAG index from the KB."""
    count = rebuild_index()
    return {"status": "ok", "documents_indexed": count}


@router.get("/rag/search")
async def rag_search(q: str, n: int = 5):
    """Search the RAG index (for debugging)."""
    from backend.rag.rag_service import retrieve
    results = retrieve(q, n_results=n)
    # Clean _doc from results for display
    for r in results:
        r.pop("_doc", None)
    return results
