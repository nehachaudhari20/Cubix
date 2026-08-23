"""Read helpers for platform dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.blue_team.fraudshield import load_fraudshield
from backend.red_team.agent_helpers import OfflineKnowledge

from .models import CampaignEvent, LoopRun, SchedulerConfig
from .schemas import CampaignEventOut, LoopRunOut, SchedulerConfigOut, SystemStatus
from .scheduler import LoopScheduler


def scheduler_config_out(row: SchedulerConfig) -> SchedulerConfigOut:
    return SchedulerConfigOut(
        enabled=row.enabled,
        interval_minutes=row.interval_minutes,
        families=row.families,
        skip_train_v1=row.skip_train_v1,
        auto_swap=row.auto_swap,
        fresh_buffer=row.fresh_buffer,
        last_run_id=row.last_run_id,
        next_run_at=row.next_run_at,
        updated_at=row.updated_at,
    )


def loop_run_out(session: Session, run: LoopRun, include_events: bool = False) -> LoopRunOut:
    events: List[CampaignEventOut] = []
    if include_events:
        rows = (
            session.query(CampaignEvent)
            .filter(CampaignEvent.loop_run_id == run.id)
            .order_by(CampaignEvent.created_at)
            .all()
        )
        events = [
            CampaignEventOut(
                id=e.id,
                loop_run_id=e.loop_run_id,
                family_id=e.family_id,
                family_name=e.family_name,
                step=e.step,
                sandbox_decision=e.sandbox_decision,
                evasion_outcome=e.evasion_outcome,
                ml_score=e.ml_score,
                amount=e.amount,
                created_at=e.created_at,
            )
            for e in rows
        ]

    return LoopRunOut(
        id=run.id,
        status=run.status,
        trigger=run.trigger,
        started_at=run.started_at,
        finished_at=run.finished_at,
        families_count=run.families_count,
        skip_train_v1=run.skip_train_v1,
        swap_model=run.swap_model,
        fresh_buffer=run.fresh_buffer,
        buffer_payments=run.buffer_payments,
        buffer_bypassed=run.buffer_bypassed,
        buffer_blocked=run.buffer_blocked,
        families_tested=run.families_tested,
        v1_buffer_mean=run.v1_buffer_mean,
        v2_buffer_mean=run.v2_buffer_mean,
        score_lift=run.score_lift,
        recommend_swap=run.recommend_swap,
        val_pr_auc=run.val_pr_auc,
        val_roc_auc=run.val_roc_auc,
        verify_decision=run.verify_decision,
        verify_ml_score=run.verify_ml_score,
        error_message=run.error_message,
        events=events,
    )


def get_model_status() -> Dict[str, Any]:
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    spec_path = Path(model_dir) / "features.json"
    status: Dict[str, Any] = {
        "loaded": False,
        "version": None,
        "model_type": None,
        "threshold": None,
        "spec_path": str(spec_path),
        "v2_available": (Path(model_dir) / "features_v2.json").exists(),
        "metrics": None,
    }
    model = load_fraudshield()
    if model:
        status.update({
            "loaded": True,
            "version": model.version,
            "model_type": model.model_type,
            "threshold": model.threshold,
        })
    else:
        from backend.blue_team.fraudshield import LOAD_ERROR

        status["load_error"] = LOAD_ERROR.get("reason")
    metrics_path = Path(model_dir) / "model_metrics.json"
    if metrics_path.exists():
        with open(metrics_path) as f:
            status["metrics"] = json.load(f)
    hardening_path = Path(model_dir) / "hardening_report.json"
    if hardening_path.exists():
        with open(hardening_path) as f:
            status["hardening_report"] = json.load(f)
    return status


def get_system_status(session: Session) -> SystemStatus:
    kb = OfflineKnowledge()
    buffer = EvidenceBuffer()
    scheduler = LoopScheduler.get()
    sched_row = scheduler.get_config()

    latest = session.query(LoopRun).order_by(desc(LoopRun.started_at)).first()
    latest_out = loop_run_out(session, latest, include_events=False) if latest else None

    return SystemStatus(
        kb=kb.kb_stats(),
        buffer=buffer.stats(),
        model=get_model_status(),
        scheduler=scheduler_config_out(sched_row),
        latest_run=latest_out,
        running_loop=scheduler.running_loop_id,
    )
