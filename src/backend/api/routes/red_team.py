"""Red Team API — campaign reasoning, plans, payloads and memory."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.platform.database import SessionLocal
from backend.platform.models import Campaign, Observation

router = APIRouter(prefix="/api/red", tags=["Red Team"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _loads(raw: Optional[str], fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _campaign_summary(c: Campaign) -> Dict[str, Any]:
    return {
        "id": c.id,
        "loop_run_id": c.loop_run_id,
        "family_id": c.family_id,
        "family_name": c.family_name,
        "lifecycle_stage": c.lifecycle_stage,
        "objective": c.objective,
        "selected_variant": c.selected_variant,
        "novelty_score": c.novelty_score,
        "success_probability": c.success_probability,
        "steps_total": c.steps_total,
        "steps_bypassed": c.steps_bypassed,
        "steps_blocked": c.steps_blocked,
        "outcome": c.outcome,
        "created_at": c.created_at,
    }


@router.get("/campaigns")
async def list_campaigns(
    limit: int = Query(default=50, ge=1, le=500),
    loop_run_id: Optional[str] = None,
    outcome: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Campaign list for the Red Team browser."""
    query = db.query(Campaign)
    if loop_run_id:
        query = query.filter(Campaign.loop_run_id == loop_run_id)
    if outcome:
        query = query.filter(Campaign.outcome == outcome)
    rows = query.order_by(desc(Campaign.created_at)).limit(limit).all()
    return [_campaign_summary(c) for c in rows]


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, db: Session = Depends(get_db)):
    """Full reasoning trace: why this attack was chosen, planned and generated."""
    c = db.get(Campaign, campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    observations = (
        db.query(Observation)
        .filter(Observation.campaign_id == campaign_id)
        .order_by(Observation.step)
        .all()
    )

    detail = _campaign_summary(c)
    detail.update({
        "hypothesis": _loads(c.hypothesis_json, {}),
        "plan": _loads(c.plan_json, {}),
        "payloads": _loads(c.payloads_json, []),
        "memory": _loads(c.memory_json, []),
        "observations": [
            {
                "id": o.id,
                "step": o.step,
                "action_type": o.action_type,
                "target_control": o.target_control,
                "expected_outcome": o.expected_outcome,
                "decision": o.decision,
                "reason": o.reason,
                "evasion_outcome": o.evasion_outcome,
                "ml_score": o.ml_score,
                "risk_score": o.risk_score,
                "amount": o.amount,
                "control_triggers": _loads(o.control_triggers_json, []),
            }
            for o in observations
        ],
    })
    return detail


@router.get("/memory")
async def list_memory(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Flattened memory entries across campaigns — what the attacker has learned."""
    rows = db.query(Campaign).order_by(desc(Campaign.created_at)).limit(limit).all()
    entries: List[Dict[str, Any]] = []
    for c in rows:
        for m in _loads(c.memory_json, []):
            entries.append({
                **m,
                "campaign_id": c.id,
                "family_id": c.family_id,
                "family_name": c.family_name,
            })
    return entries


@router.get("/coverage")
async def family_coverage(db: Session = Depends(get_db)):
    """Which attack families have been exercised, and how they fared."""
    from backend.red_team.agent_helpers import OfflineKnowledge

    kb = OfflineKnowledge()
    tested: Dict[str, Dict[str, Any]] = {}
    for c in db.query(Campaign).all():
        entry = tested.setdefault(
            c.family_id,
            {"family_id": c.family_id, "family_name": c.family_name, "campaigns": 0,
             "bypassed": 0, "blocked": 0},
        )
        entry["campaigns"] += 1
        entry["bypassed"] += c.steps_bypassed
        entry["blocked"] += c.steps_blocked

    stats = kb.kb_stats()
    return {
        "total_families": stats.get("total_families", 0),
        "simulatable_families": stats.get("simulatable_families", 0),
        "tested_families": len(tested),
        "families": sorted(tested.values(), key=lambda x: -x["bypassed"]),
    }
