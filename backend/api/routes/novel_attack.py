"""Novel Attack Generator — LLM-powered attack discovery endpoint."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/novel-attack", tags=["novel-attack"])

# Store generated attacks
_novel_attacks: Dict[str, Dict[str, Any]] = {}


class NovelAttackRequest(BaseModel):
    focus_area: str = "AI-agent payment fraud"
    num_attacks: int = 3
    model: str = "command-r-08-2024"  # Cohere default
    include_kb_context: bool = True
    target_surface: Optional[str] = None  # payment, auth, device, kyc, etc.


@router.post("/generate")
async def generate_novel_attacks(req: NovelAttackRequest):
    """Generate novel attack hypotheses using LLM."""
    from backend.llm.provider import get_llm, invoke_text
    from backend.red_team.agent_helpers import OfflineKnowledge
    
    # Get KB context if requested
    kb_context = ""
    if req.include_kb_context:
        try:
            kb = OfflineKnowledge()
            families = [f.get("attack_id", "") for f in kb.families[:10]]
            kb_context = f"\n\nKnown attack families (avoid duplicates): {', '.join(families)}"
        except Exception:
            pass
    
    system_prompt = """You are Dr. Shadow, a world-class payment fraud researcher and Red Team architect.

Your role is to discover NOVEL attack vectors that could bypass current fraud detection systems.
You think like an advanced persistent threat actor, but your purpose is DEFENSIVE — finding gaps before criminals do.

Key principles:
1. Think beyond known patterns — combine multiple attack surfaces
2. Consider AI-agent abuse (autonomous agents making payments)
3. Focus on control gaps, not just attack methods
4. Every attack must be SIMULABLE in a sandbox environment
5. Provide actionable intelligence for Blue Team hardening"""

    user_prompt = f"""Generate {req.num_attacks} NOVEL attack hypotheses for: {req.focus_area}

For each attack, provide a JSON object with these fields:
{{
    "name": "Attack name (concise, memorable)",
    "primary_family": "Attack family ID (e.g., AG-001 for agent abuse)",
    "target_stages": ["stage1", "stage2"],
    "novelty_score": 0.0-1.0,
    "success_probability": 0.0-1.0,
    "attack_flow": [
        "Step 1: description",
        "Step 2: description",
        "Step 3: description"
    ],
    "controls_targeted": ["control1", "control2"],
    "evasion_technique": "How this evades current controls",
    "detection_signals": ["signal1", "signal2"],
    "blue_team_recommendation": "What Blue Team should add to detect this",
    "composite_families": ["optional partner family IDs"]
}}

{kb_context}

Requirements:
- Focus on {req.target_surface or 'ALL surfaces'} attack surface
- At least 1 attack must be a COMPOSITE (multi-family)
- Novelty score must be > 0.7 (truly novel, not well-known)
- Provide realistic attack flows with specific steps
- Consider AI-agent and GenAI abuse scenarios

Return ONLY a JSON array of attack objects."""

    # Resolve model — pass None to use provider default
    model_id = req.model if req.model else None
    
    start_time = time.time()
    
    try:
        llm = get_llm(model=model_id, temperature=0.6)
        if not llm:
            return {"error": "LLM not configured", "hint": "Set COHERE_API_KEY and RED_TEAM_USE_LLM=true in .env"}
        
        response = invoke_text(llm, system_prompt, user_prompt)
        elapsed = time.time() - start_time
        
        if not response:
            return {"error": "No response from LLM", "model": model_id, "time": elapsed}
        
        # Parse JSON from response
        attacks = []
        try:
            # Try to extract JSON array from response
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                attacks = json.loads(response[json_start:json_end])
            else:
                # Try single object
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    attacks = [json.loads(response[json_start:json_end])]
        except json.JSONDecodeError:
            # Return raw response if JSON parsing fails
            attacks = [{"raw_response": response, "parse_error": "Could not extract structured attacks"}]
        
        # Store results
        result_id = f"novel_{uuid.uuid4().hex[:8]}"
        result = {
            "id": result_id,
            "model": model_id,
            "focus_area": req.focus_area,
            "num_generated": len(attacks),
            "attacks": attacks,
            "elapsed_seconds": round(elapsed, 2),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "raw_response": response,
        }
        _novel_attacks[result_id] = result
        
        return result
        
    except Exception as e:
        elapsed = time.time() - start_time
        return {"error": str(e), "model": model_id, "time": elapsed}


@router.get("/history")
async def get_history():
    """Get all generated novel attacks."""
    return {"attacks": list(_novel_attacks.values()), "total": len(_novel_attacks)}


@router.get("/{attack_id}")
async def get_attack(attack_id: str):
    """Get a specific novel attack."""
    if attack_id not in _novel_attacks:
        return {"error": "Not found"}
    return _novel_attacks[attack_id]
