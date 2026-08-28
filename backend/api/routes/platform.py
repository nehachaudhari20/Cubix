"""Platform dashboard API — loop runs, scheduler, system status."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List

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
from backend.platform.status_service import get_system_status, loop_run_out, scheduler_config_out

EVAL_DIR = Path(__file__).resolve().parents[3] / "data" / "evaluation"

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


# ---------------------------------------------------------------------------
# Reports — evaluation & failure analysis per loop run
# ---------------------------------------------------------------------------

def _sanitize_nan(obj: Any) -> Any:
    """Recursively replace NaN/Inf floats with None so the response is JSON-safe."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _load_run_report(run_id: str, filename_prefix: str) -> Dict[str, Any]:
    """Load a JSON report saved by the loop runner for a given run_id.
    Falls back to the most recent report of the same type if the exact ID isn't found."""
    path = EVAL_DIR / f"{filename_prefix}_{run_id}.json"
    if path.exists():
        with open(path) as f:
            return _sanitize_nan(json.load(f))

    # Fallback: find the most recent report of this type
    matches = sorted(EVAL_DIR.glob(f"{filename_prefix}_*.json"), key=os.path.getmtime, reverse=True)
    if matches:
        with open(matches[0]) as f:
            data = json.load(f)
        data["_note"] = f"Exact run {run_id} not found; showing latest available report ({matches[0].name})"
        return _sanitize_nan(data)

    raise HTTPException(
        status_code=404,
        detail=f"No {filename_prefix} reports found. Run the loop first to generate reports.",
    )


@router.get("/runs/{run_id}/evaluation")
async def get_evaluation(run_id: str):
    """Return the Phase 11-14 evaluation report for a loop run.
    Loads directly from data/evaluation/ — works even if the DB was recreated."""
    return _load_run_report(run_id, "loop")


@router.get("/runs/{run_id}/failure-analysis")
async def get_failure_analysis(run_id: str):
    """Return the failure analysis (CTL heatmap + per-family ASR) for a loop run.
    Loads directly from data/evaluation/ — works even if the DB was recreated."""
    return _load_run_report(run_id, "failure_analysis")
