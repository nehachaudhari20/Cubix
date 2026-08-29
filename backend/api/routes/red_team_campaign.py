"""Red Team Campaign API — campaigns, timeline, safety, memory, strategy."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.safety.policy_engine import SimulationPolicyEngine

router = APIRouter(prefix="/api/v1/red-team", tags=["red-team-campaign"])

_campaign_store: Dict[str, Dict[str, Any]] = {}
_safety_engine = SimulationPolicyEngine()


class CampaignCreateRequest(BaseModel):
    attack_family: str
    composite_families: List[str] = Field(default_factory=list)
    strategy: str = "sequential"
    campaign_size: int = 12
    mutation_budget: int = 2
    max_events: int = 250


class HypothesisRequest(BaseModel):
    tested_families: List[str] = Field(default_factory=list)
    max_hypotheses: int = 5
    prefer_composites: bool = True


@router.get("/families")
async def list_families():
    """List all 57 KB attack families."""
    from backend.red_team.agent_helpers import OfflineKnowledge
    kb = OfflineKnowledge()
    families = []
    for fam in kb.families:
        families.append({
            "attack_id": fam.get("attack_id"),
            "name": fam.get("name"),
            "lifecycle_stage": fam.get("lifecycle_stage"),
            "surface": fam.get("surface", "payment"),
            "variants": fam.get("variants", []),
            "controls_targeted": fam.get("controls_targeted", []),
            "is_genai": (fam.get("genai") or {}).get("is_genai", False) if isinstance(fam.get("genai"), dict) else False,
            "simulatable": fam.get("simulatable", True),
        })
    return {"families": families, "total": len(families)}


@router.post("/hypotheses")
async def generate_hypotheses(req: HypothesisRequest):
    """Run Threat Hunter to generate attack hypotheses."""
    from backend.red_team.agents.threat_hunter import ThreatHunter
    hunter = ThreatHunter()
    output = hunter.discover(
        tested_families=req.tested_families,
        prefer_composites=req.prefer_composites,
        max_hypotheses=req.max_hypotheses,
    )
    return {
        "run_id": f"hunter_{uuid.uuid4().hex[:8]}",
        "hypotheses": [h.model_dump() for h in output.hypotheses],
        "confidence": output.confidence,
    }


@router.post("/campaigns")
async def create_campaign(req: CampaignCreateRequest):
    """Create a new controlled simulation campaign."""
    campaign_id = f"camp_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    campaign = {
        "campaign_id": campaign_id,
        "attack_family": req.attack_family,
        "composite_families": req.composite_families,
        "strategy": req.strategy,
        "campaign_size": req.campaign_size,
        "mutation_budget": req.mutation_budget,
        "status": "created",
        "safety_gate": _safety_engine.get_safety_gate_display(),
        "timeline": [
            {"agent": "Threat Hunter", "status": "waiting", "order": 1},
            {"agent": "Attack Planner", "status": "waiting", "order": 2},
            {"agent": "Attack Generator", "status": "waiting", "order": 3},
            {"agent": "Sandbox Execution", "status": "waiting", "order": 4},
            {"agent": "Failure Analyzer", "status": "waiting", "order": 5},
            {"agent": "Memory Agent", "status": "waiting", "order": 6},
            {"agent": "Strategy Layer", "status": "waiting", "order": 7},
        ],
        "events_generated": 0,
        "events_blocked": 0,
        "events_allowed": 0,
        "memory_entries": 0,
        "created_at": now,
    }
    _campaign_store[campaign_id] = campaign
    return campaign


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    if campaign_id not in _campaign_store:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_store[campaign_id]


@router.get("/campaigns/{campaign_id}/timeline")
async def get_timeline(campaign_id: str):
    if campaign_id not in _campaign_store:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"campaign_id": campaign_id, "timeline": _campaign_store[campaign_id]["timeline"]}


@router.get("/campaigns/{campaign_id}/safety")
async def get_safety(campaign_id: str):
    budget = _safety_engine.get_budget()
    return {"campaign_id": campaign_id, "gate": _safety_engine.get_safety_gate_display(), "budget": budget.model_dump()}


@router.get("/campaigns/{campaign_id}/memory")
async def get_memory(campaign_id: str):
    return {"campaign_id": campaign_id, "memories": [], "total_entries": 0}


@router.get("/campaigns/{campaign_id}/strategy")
async def get_strategy(campaign_id: str):
    if campaign_id not in _campaign_store:
        raise HTTPException(status_code=404, detail="Campaign not found")
    c = _campaign_store[campaign_id]
    return {"campaign_id": campaign_id, "current_family": c["attack_family"], "mutations_used": 0, "mutations_budget": c["mutation_budget"], "next_action": "continue", "reason": "Campaign created — awaiting execution"}


@router.post("/campaigns/{campaign_id}/stop")
async def stop_campaign(campaign_id: str):
    if campaign_id not in _campaign_store:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _campaign_store[campaign_id]["status"] = "stopped"
    return {"campaign_id": campaign_id, "status": "stopped", "message": "Campaign stopped safely"}
