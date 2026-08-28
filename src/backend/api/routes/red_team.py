"""Red Team API — lab generate+score, campaign reasoning, memory."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.platform.database import SessionLocal
from backend.platform.models import Campaign, Observation, RedTeamRun
from backend.red_team.lab import (
    LabRequest,
    catalog,
    chat_novel,
    failing_context,
    run_detail,
    run_lab,
    run_summary,
    synthesize_novel,
)

router = APIRouter(prefix="/api/red", tags=["Red Team"])


class NovelFamilyIn(BaseModel):
    name: str = "Novel beneficiary anomaly"
    description: str = ""
    lifecycle_stage: str = "Payment Initiation"
    generate_image: bool = True
    variants: Optional[List[str]] = None
    detection_signals: Optional[List[str]] = None


class ChatTurnIn(BaseModel):
    message: str
    run_id: Optional[str] = None
    history: List[Dict[str, str]] = []


class LabRunIn(BaseModel):
    mode: str = "standard"
    family_id: str = ""
    variant: str = ""
    difficulty: str = "MEDIUM"
    population: str = "normal_customers"
    scale: int = 1000
    seed: int = 424242
    novel: Optional[NovelFamilyIn] = None
    generate_image: bool = False


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


@router.get("/lab/catalog")
async def lab_catalog(db: Session = Depends(get_db)):
    """Known families plus novel families already generated in this lab."""
    data = catalog()
    seen = {f["attack_id"] for f in data["families"]}
    novels = (
        db.query(RedTeamRun)
        .filter(RedTeamRun.is_novel.is_(True))
        .order_by(desc(RedTeamRun.created_at))
        .all()
    )
    extra = []
    for run in novels:
        if run.family_id in seen:
            continue
        try:
            result = json.loads(run.result_json or "{}")
        except json.JSONDecodeError:
            result = {}
        fam = (result.get("family") or {})
        extra.append({
            "attack_id": run.family_id,
            "name": run.family_name,
            "lifecycle_stage": fam.get("lifecycle_stage") or "Novel",
            "simulation_type": "Novel",
            "variants": [{"code": run.variant_code, "name": run.variant}],
            "attack_flow": fam.get("attack_flow") or [],
            "detection_signals": fam.get("detection_signals") or [],
            "controls_targeted": [],
            "visual": True,
            "is_novel": True,
        })
        seen.add(run.family_id)
    data["families"] = extra + data["families"]
    return data


@router.get("/failing")
async def list_failing(run_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Existing misses the chat mutates into a novel family."""
    return failing_context(db, run_id=run_id)


@router.post("/chat")
async def chat_novel_family(body: ChatTurnIn, db: Session = Depends(get_db)):
    """Chat-type novel family: mutate what Blue already missed."""
    ctx = failing_context(db, run_id=body.run_id)
    return chat_novel(body.message, ctx, history=body.history)


@router.post("/novel")
async def create_novel_family(body: NovelFamilyIn, db: Session = Depends(get_db)):
    count = db.query(RedTeamRun).filter(RedTeamRun.is_novel.is_(True)).count()
    return synthesize_novel(body.model_dump(), existing_count=count)


@router.post("/runs")
async def create_lab_run(body: LabRunIn, db: Session = Depends(get_db)):
    """Generate a threat and score every row on the frozen Blue detector."""
    novel_count = db.query(RedTeamRun).filter(RedTeamRun.is_novel.is_(True)).count()
    try:
        result = run_lab(
            LabRequest(
                mode=body.mode,
                family_id=body.family_id,
                variant=body.variant,
                difficulty=body.difficulty,
                population=body.population,
                scale=body.scale,
                seed=body.seed,
                novel=body.novel.model_dump() if body.novel else None,
                generate_image=body.generate_image,
            ),
            novel_count=novel_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = RedTeamRun(
        id=result["id"],
        mode=result["mode"],
        family_id=result["family_id"],
        family_name=result["family_name"],
        variant=result["variant"],
        variant_code=result["variant_code"],
        difficulty=result["difficulty"],
        population=result["population"],
        scale=result["scale"],
        seed=result["seed"],
        is_novel=result["is_novel"],
        generate_image=result["generate_image"],
        generated=result["generated"],
        detected=result["detected"],
        missed=result["missed"],
        attack_success=result["attack_success"],
        detection_rate=result["detection_rate"],
        precision=result["precision"],
        pr_auc=result["pr_auc"],
        threshold=result["threshold"],
        model_version=result["model_version"],
        result_json=json.dumps(result["result"]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return run_detail(row)


@router.get("/runs")
async def list_lab_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = db.query(RedTeamRun).order_by(desc(RedTeamRun.created_at)).limit(limit).all()
    return [run_summary(r) for r in rows]


@router.get("/runs/{run_id}")
async def get_lab_run(run_id: str, db: Session = Depends(get_db)):
    row = db.get(RedTeamRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run_detail(row)


@router.post("/runs/{run_id}/replay")
async def replay_lab_run(run_id: str, db: Session = Depends(get_db)):
    """Rescore the same seed and setup on the current Blue model."""
    prior = db.get(RedTeamRun, run_id)
    if not prior:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    try:
        prior_result = json.loads(prior.result_json or "{}")
    except json.JSONDecodeError:
        prior_result = {}
    family = prior_result.get("family") or {}
    novel = None
    if prior.is_novel:
        novel = {
            "name": prior.family_name,
            "description": family.get("description") or "",
            "lifecycle_stage": family.get("lifecycle_stage") or "Novel",
            "generate_image": prior.generate_image,
        }
    novel_count = db.query(RedTeamRun).filter(RedTeamRun.is_novel.is_(True)).count()
    result = run_lab(
        LabRequest(
            mode=prior.mode,
            family_id=prior.family_id,
            variant=prior.variant_code or prior.variant,
            difficulty=prior.difficulty,
            population=prior.population,
            scale=prior.scale,
            seed=prior.seed,
            novel=novel,
            generate_image=prior.generate_image,
        ),
        novel_count=novel_count,
    )
    result["replay_of"] = prior.id
    row = RedTeamRun(
        id=result["id"],
        mode=result["mode"],
        family_id=result["family_id"],
        family_name=result["family_name"],
        variant=result["variant"],
        variant_code=result["variant_code"],
        difficulty=result["difficulty"],
        population=result["population"],
        scale=result["scale"],
        seed=result["seed"],
        is_novel=result["is_novel"],
        generate_image=result["generate_image"],
        generated=result["generated"],
        detected=result["detected"],
        missed=result["missed"],
        attack_success=result["attack_success"],
        detection_rate=result["detection_rate"],
        precision=result["precision"],
        pr_auc=result["pr_auc"],
        threshold=result["threshold"],
        model_version=result["model_version"],
        result_json=json.dumps({**result["result"], "replay_of": prior.id}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return run_detail(row)


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
