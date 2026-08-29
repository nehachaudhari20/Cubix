"""Knowledge Base API routes."""

from typing import List, Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.knowledge.loader import KnowledgeLoader

router = APIRouter(prefix="/api/kb", tags=["Knowledge Base"])
loader = KnowledgeLoader()


class AttackFamilyResponse(BaseModel):
    attack_id: str
    name: str
    variants: List[str]
    lifecycle_stage: str
    genai_classification: str
    simulation_type: str
    prerequisites: List[str]
    attack_flow: List[str]
    detection_signals: List[dict]
    controls_targeted: List[str]
    evidence_confidence: str
    surface: Optional[str] = None
    objective: Optional[str] = None
    attacker: Optional[str] = None
    target: Optional[str] = None
    technique_ids: List[str] = []


class SignalResponse(BaseModel):
    signal_name: str
    category: str
    description: str
    detection_method: str
    false_positive_risk: str
    cross_account_needed: bool


class LifecycleStageResponse(BaseModel):
    stage: str
    controls: List[str]


@router.get("/stats")
async def get_stats():
    from backend.red_team.kb_campaign_builder import is_simulatable

    simulatable = [f for f in loader.families if is_simulatable(f)]
    simulatable_ids = [f.get("attack_id") for f in simulatable if f.get("attack_id")]
    return {
        "total_families": len(loader.families),
        "total_signals": len(loader.signals),
        "total_stages": len(loader.stages),
        "simulatable_families": len(simulatable),
        "simulatable_ids": simulatable_ids,
        "families_by_stage": {
            stage: len(loader.get_families_by_stage(stage))
            for stage in loader.get_all_controls().keys()
        },
    }


@router.get("/families", response_model=List[AttackFamilyResponse])
async def get_all_families(
    stage: Optional[str] = None,
    genai_class: Optional[str] = None,
    limit: int = 100,
):
    families = loader.families
    if stage:
        families = [f for f in families if f.get("lifecycle_stage") == stage]
    if genai_class:
        families = [f for f in families if f.get("genai_classification") == genai_class]
    return families[:limit]


@router.get("/families/{family_id}", response_model=AttackFamilyResponse)
async def get_family(family_id: str):
    family = loader.get_family(family_id)
    if not family:
        raise HTTPException(status_code=404, detail=f"Family {family_id} not found")
    return family


@router.get("/signals", response_model=List[SignalResponse])
async def get_all_signals(category: Optional[str] = None, limit: int = 200):
    signals = loader.signals
    if category:
        signals = [s for s in signals if s.get("category") == category]
    return signals[:limit]


@router.get("/stages", response_model=List[LifecycleStageResponse])
async def get_all_stages():
    return loader.stages


@router.get("/stages/controls")
async def get_all_controls():
    return loader.get_all_controls()


@router.get("/stages/{stage}/controls")
async def get_controls_for_stage(stage: str):
    decoded_stage = unquote(stage)
    controls = loader.get_all_controls()
    if decoded_stage in controls:
        return {"stage": decoded_stage, "controls": controls[decoded_stage]}
    for key in controls:
        if key.lower() == decoded_stage.lower():
            return {"stage": key, "controls": controls[key]}
    raise HTTPException(status_code=404, detail=f"Stage '{decoded_stage}' not found")
