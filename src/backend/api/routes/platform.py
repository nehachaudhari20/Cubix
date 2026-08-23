"""Platform dashboard API — loop runs, scheduler, system status."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.platform.database import SessionLocal, init_db
from backend.platform.loop_runner import LoopRunConfig
from backend.platform.models import LoopRun
from backend.platform.schemas import (
    LoopRunOut,
    LoopRunRequest,
    SchedulerConfigOut,
    SchedulerConfigUpdate,
    SystemStatus,
)
from backend.platform.scheduler import LoopScheduler
from backend.platform.status_service import (
    get_model_status,
    get_system_status,
    loop_run_out,
    scheduler_config_out,
)

router = APIRouter(prefix="/api/platform", tags=["Platform"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/status", response_model=SystemStatus)
async def platform_status(db: Session = Depends(get_db)):
    return get_system_status(db)


@router.get("/buffer")
async def buffer_stats():
    return EvidenceBuffer().stats()


@router.get("/buffer/recent")
async def buffer_recent(limit: int = 25):
    records = EvidenceBuffer().read_all()
    recent = records[-limit:]
    return [r.model_dump() for r in reversed(recent)]


@router.get("/metrics")
async def overview_metrics(db: Session = Depends(get_db)):
    """Live KPI tiles for the Command Center."""
    from datetime import datetime, timedelta, timezone

    from backend.platform.models import Campaign, Observation

    payments = (
        db.query(Observation)
        .filter(Observation.action_type == "initiate_payment")
        .all()
    )
    total = len(payments)
    bypassed = sum(1 for o in payments if o.decision == "ALLOW")
    challenged = sum(1 for o in payments if o.decision == "CHALLENGE")
    blocked = sum(1 for o in payments if o.decision == "BLOCK")

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    campaigns_today = (
        db.query(Campaign).filter(Campaign.created_at >= since).count()
    )

    model = get_model_status()
    metrics = (model.get("metrics") or {}).get("results", [])
    active = next(
        (m for m in metrics if m.get("model") == model.get("model_type")),
        metrics[-1] if metrics else {},
    )

    # A control gap is a payment allowed with no control objection at all.
    gaps = sum(
        1 for o in payments
        if o.decision == "ALLOW" and not (o.control_triggers_json or "[]").strip("[] \n")
    )

    return {
        "attack_success_rate": round(bypassed / total, 4) if total else 0.0,
        "attacks_executed": total,
        "bypassed": bypassed,
        "challenged": challenged,
        "blocked": blocked,
        "campaigns_today": campaigns_today,
        "campaigns_total": db.query(Campaign).count(),
        "control_gaps": gaps,
        "model_version": model.get("version"),
        "model_type": model.get("model_type"),
        "threshold": model.get("threshold"),
        "f1": active.get("f1"),
        "precision": active.get("precision"),
        "recall": active.get("recall"),
        "pr_auc": active.get("pr_auc"),
        "roc_auc": active.get("roc_auc"),
    }


@router.get("/ticker")
async def event_ticker(limit: int = 20, db: Session = Depends(get_db)):
    """Most recent sandbox observations for the live feed."""
    from backend.platform.models import Observation

    rows = (
        db.query(Observation)
        .order_by(desc(Observation.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": o.id,
            "campaign_id": o.campaign_id,
            "family_id": o.family_id,
            "family_name": o.family_name,
            "step": o.step,
            "action_type": o.action_type,
            "decision": o.decision,
            "reason": o.reason,
            "ml_score": o.ml_score,
            "risk_score": o.risk_score,
            "amount": o.amount,
            "location_region": o.location_region,
            "created_at": o.created_at,
        }
        for o in rows
    ]


@router.get("/runs", response_model=List[LoopRunOut])
async def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    runs = db.query(LoopRun).order_by(desc(LoopRun.started_at)).limit(limit).all()
    return [loop_run_out(db, r, include_events=False) for r in runs]


@router.get("/runs/{run_id}", response_model=LoopRunOut)
async def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(LoopRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return loop_run_out(db, run, include_events=True)


@router.post("/loop/run")
async def trigger_loop(request: LoopRunRequest):
    scheduler = LoopScheduler.get()
    if scheduler.running_loop_id:
        raise HTTPException(
            status_code=409,
            detail=f"Loop already running: {scheduler.running_loop_id}",
        )
    try:
        run_id = scheduler.run_with_config(
            LoopRunConfig(
                families=request.families,
                skip_train_v1=request.skip_train_v1,
                swap_model=request.swap_model,
                fresh_buffer=request.fresh_buffer,
                trigger="manual",
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"run_id": run_id, "status": "started"}


@router.get("/loop/running")
async def running_loop():
    scheduler = LoopScheduler.get()
    return {"running": scheduler.running_loop_id is not None, "run_id": scheduler.running_loop_id}


@router.get("/scheduler", response_model=SchedulerConfigOut)
async def get_scheduler_config():
    row = LoopScheduler.get().get_config()
    return scheduler_config_out(row)


@router.put("/scheduler", response_model=SchedulerConfigOut)
async def update_scheduler_config(update: SchedulerConfigUpdate):
    payload = update.model_dump(exclude_none=True)
    row = LoopScheduler.get().update_config(**payload)
    return scheduler_config_out(row)
