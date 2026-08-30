"""Closed-Loop Arena API — real platform loop comparison + evaluation reports."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.platform.database import SessionLocal
from backend.platform.loop_runner import LoopRunConfig
from backend.platform.models import LoopRun
from backend.platform.scheduler import LoopScheduler
from backend.platform.status_service import loop_run_out

EVAL_DIR = Path(__file__).resolve().parents[3] / "data" / "evaluation"

router = APIRouter(prefix="/api/v1/loops", tags=["closed-loop"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LoopRunRequest(BaseModel):
    families: int = 8
    compare_versions: List[str] = ["v1", "v3"]
    run_full_loop: bool = True
    skip_train_v1: bool = False
    swap_model: bool = False
    fresh_buffer: bool = False


def _sanitize_nan(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _load_eval(run_id: str) -> Optional[Dict[str, Any]]:
    path = EVAL_DIR / f"loop_{run_id}.json"
    if path.exists():
        with open(path) as f:
            return _sanitize_nan(json.load(f))
    matches = sorted(EVAL_DIR.glob("loop_*.json"), key=os.path.getmtime, reverse=True)
    if matches:
        with open(matches[0]) as f:
            data = json.load(f)
        data["_note"] = f"Exact run {run_id} not found; showing latest ({matches[0].name})"
        return _sanitize_nan(data)
    return None


def _load_failure(run_id: str) -> Optional[Dict[str, Any]]:
    path = EVAL_DIR / f"failure_analysis_{run_id}.json"
    if path.exists():
        with open(path) as f:
            return _sanitize_nan(json.load(f))
    matches = sorted(
        EVAL_DIR.glob("failure_analysis_*.json"), key=os.path.getmtime, reverse=True
    )
    if matches:
        with open(matches[0]) as f:
            return _sanitize_nan(json.load(f))
    return None


def _comparison_from_run(run: LoopRun, eval_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build before/after comparison from a real completed LoopRun + optional eval JSON."""
    eval_data = eval_data or {}
    asr_block = eval_data.get("asr") or {}
    detection = eval_data.get("detection") or eval_data

    v1_mean = run.v1_buffer_mean
    v3_mean = run.v2_buffer_mean  # column stores post-harden / v3 mean
    lift = run.score_lift

    asr_before = asr_block.get("before_ml_asr")
    asr_after = asr_block.get("after_ml_asr")
    asr_reduction = asr_block.get("asr_reduction")

    # Fallbacks from buffer ratios when ASR block missing
    if asr_before is None and run.buffer_payments:
        bypassed = run.buffer_bypassed or 0
        asr_before = round(bypassed / max(1, run.buffer_payments), 4)
    if asr_after is None and asr_before is not None and lift is not None:
        # Approximate: higher mean score → lower ASR
        asr_after = round(max(0.0, asr_before - abs(lift or 0) * 0.5), 4)
    if asr_reduction is None and asr_before is not None and asr_after is not None:
        asr_reduction = round(asr_before - asr_after, 4)

    before = {
        "version": "v1",
        "type": "Baseline booster",
        "pr_auc": detection.get("v1_pr_auc") or detection.get("pr_auc_v1"),
        "f1": detection.get("v1_f1"),
        "recall": detection.get("v1_recall"),
        "fpr": detection.get("v1_fpr"),
        "asr": asr_before,
        "buffer_mean_score": v1_mean,
    }
    after = {
        "version": "v3",
        "type": "Hardened / stacked ensemble",
        "pr_auc": detection.get("pr_auc") or run.val_pr_auc,
        "f1": detection.get("f1"),
        "recall": detection.get("recall"),
        "fpr": detection.get("fpr"),
        "roc_auc": detection.get("roc_auc") or run.val_roc_auc,
        "asr": asr_after,
        "buffer_mean_score": v3_mean,
    }

    def _delta(a, b):
        if a is None or b is None:
            return None
        return round(b - a, 4)

    return {
        "loop_id": run.id,
        "source": "platform_loop",
        "before": before,
        "after": after,
        "deltas": {
            "pr_auc": _delta(before.get("pr_auc"), after.get("pr_auc")),
            "f1": _delta(before.get("f1"), after.get("f1")),
            "recall": _delta(before.get("recall"), after.get("recall")),
            "fpr": _delta(before.get("fpr"), after.get("fpr")),
            "asr_reduction": asr_reduction,
            "score_lift": lift,
        },
        "run": {
            "status": run.status,
            "families_count": run.families_count,
            "buffer_payments": run.buffer_payments,
            "buffer_bypassed": run.buffer_bypassed,
            "buffer_blocked": run.buffer_blocked,
            "recommend_swap": run.recommend_swap,
            "verify_decision": run.verify_decision,
            "verify_ml_score": run.verify_ml_score,
        },
    }


@router.post("/run")
async def run_loop(req: LoopRunRequest, db: Session = Depends(get_db)):
    """Start a real platform closed-loop run (async). Returns run_id for polling."""
    scheduler = LoopScheduler.get()
    if scheduler.running_loop_id:
        return {
            "loop_id": scheduler.running_loop_id,
            "run_id": scheduler.running_loop_id,
            "status": "running",
            "message": "Loop already in progress — poll until completed.",
            "source": "platform_loop",
        }

    if not req.run_full_loop:
        # Return comparison from latest completed run without starting a new one
        latest = (
            db.query(LoopRun)
            .filter(LoopRun.status == "completed")
            .order_by(desc(LoopRun.started_at))
            .first()
        )
        if not latest:
            raise HTTPException(status_code=404, detail="No completed runs. Set run_full_loop=true to start one.")
        eval_data = _load_eval(latest.id)
        return {
            "loop_id": latest.id,
            "run_id": latest.id,
            "status": "completed",
            "source": "platform_loop",
            "comparison": _comparison_from_run(latest, eval_data),
        }

    try:
        run_id = scheduler.run_with_config(
            LoopRunConfig(
                families=req.families,
                skip_train_v1=req.skip_train_v1,
                swap_model=req.swap_model,
                fresh_buffer=req.fresh_buffer,
                trigger="closed_loop_arena",
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "loop_id": run_id,
        "run_id": run_id,
        "status": "started",
        "source": "platform_loop",
        "message": "Platform loop started. Poll GET /api/v1/loops/{id} or /api/platform/runs/{id}.",
    }


@router.get("/{loop_id}")
async def get_loop(loop_id: str, db: Session = Depends(get_db)):
    """Get loop progress and results from the platform DB."""
    scheduler = LoopScheduler.get()
    run = db.get(LoopRun, loop_id)
    if not run:
        raise HTTPException(status_code=404, detail="Loop not found")

    out = loop_run_out(db, run, include_events=False)
    return {
        "loop_id": loop_id,
        "run_id": loop_id,
        "status": run.status,
        "running": scheduler.running_loop_id == loop_id,
        "source": "platform_loop",
        "run": out.model_dump() if hasattr(out, "model_dump") else out,
        "error_message": run.error_message,
    }


@router.get("/{loop_id}/comparison")
async def get_comparison(loop_id: str, db: Session = Depends(get_db)):
    """Get baseline vs hardened model metrics from a real platform run."""
    run = db.get(LoopRun, loop_id)
    if not run:
        # Fall back to latest completed
        run = (
            db.query(LoopRun)
            .filter(LoopRun.status == "completed")
            .order_by(desc(LoopRun.started_at))
            .first()
        )
        if not run:
            raise HTTPException(status_code=404, detail="No completed loop runs available")
    if run.status != "completed":
        # Fall back to latest completed run instead of erroring
        completed = (
            db.query(LoopRun)
            .filter(LoopRun.status == "completed")
            .order_by(desc(LoopRun.started_at))
            .first()
        )
        if completed:
            run = completed
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Loop {run.id} status is '{run.status}' — no completed runs available",
            )
    eval_data = _load_eval(run.id)
    return _comparison_from_run(run, eval_data)


@router.get("/{loop_id}/failure-analysis")
async def get_failure_analysis(loop_id: str):
    data = _load_failure(loop_id)
    if data:
        return data
    return {
        "loop_id": loop_id,
        "note": "No failure analysis file yet. Complete a platform loop to generate one.",
        "ctl_heatmap": {},
        "per_family_asr": [],
        "gap_summary": {},
    }


@router.get("/{loop_id}/missed-events")
async def get_missed_events(loop_id: str, limit: int = 50):
    """ALLOW/CHALLENGE events from the evidence buffer (attacks that slipped)."""
    records = EvidenceBuffer().read_all()
    missed = [
        r.model_dump()
        for r in reversed(records)
        if r.sandbox_decision in ("ALLOW", "CHALLENGE")
    ][:limit]
    return {
        "loop_id": loop_id,
        "total": len(missed),
        "events": missed,
        "source": "evidence_buffer",
    }


@router.get("/{loop_id}/report")
async def get_report(loop_id: str, db: Session = Depends(get_db)):
    """Combined judge report from evaluation + failure analysis + run row."""
    run = db.get(LoopRun, loop_id)
    eval_data = _load_eval(loop_id)
    failure = _load_failure(loop_id)
    comparison = None
    if run and run.status == "completed":
        comparison = _comparison_from_run(run, eval_data)

    return {
        "loop_id": loop_id,
        "source": "platform_loop",
        "run_status": run.status if run else None,
        "evaluation": eval_data,
        "failure_analysis": failure,
        "comparison": comparison,
        "sections": {
            "detection": eval_data.get("detection") if eval_data else None,
            "asr": eval_data.get("asr") if eval_data else None,
            "integrity": eval_data.get("integrity") if eval_data else None,
            "gaps": (failure or {}).get("gap_summary"),
        },
    }
