"""Blue Team API — model lineage, feature importance, buffer and hardening deltas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.blue_team.fraudshield import load_fraudshield
from backend.platform.database import SessionLocal
from backend.platform.models import ModelVersion
from backend.platform.status_service import get_model_status

router = APIRouter(prefix="/api/blue", tags=["Blue Team"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/models")
async def model_versions(db: Session = Depends(get_db)):
    """Version history with metric deltas between consecutive versions."""
    rows = db.query(ModelVersion).order_by(ModelVersion.trained_at).all()

    history: List[Dict[str, Any]] = []
    previous: Optional[ModelVersion] = None
    for r in rows:
        def delta(current, prior):
            if current is None or prior is None:
                return None
            return round(current - prior, 4)

        history.append({
            "id": r.id,
            "version": r.version,
            "model_type": r.model_type,
            "parent_version": r.parent_version,
            "trained_at": r.trained_at,
            "loop_run_id": r.loop_run_id,
            "baseline_rows": r.baseline_rows,
            "buffer_rows": r.buffer_rows,
            "buffer_families": [f for f in (r.buffer_families or "").split(", ") if f],
            "feature_count": r.feature_count,
            "decision_threshold": r.decision_threshold,
            "val_pr_auc": r.val_pr_auc,
            "val_roc_auc": r.val_roc_auc,
            "buffer_mean_score": r.buffer_mean_score,
            "score_lift": r.score_lift,
            "baseline_fraud_recall": r.baseline_fraud_recall,
            "promoted": r.promoted,
            "delta_pr_auc": delta(r.val_pr_auc, previous.val_pr_auc if previous else None),
            "delta_roc_auc": delta(r.val_roc_auc, previous.val_roc_auc if previous else None),
            "delta_recall": delta(
                r.baseline_fraud_recall, previous.baseline_fraud_recall if previous else None
            ),
        })
        previous = r

    return {"active": get_model_status(), "history": list(reversed(history))}


@router.get("/feature-importance")
async def feature_importance(top: int = Query(default=20, ge=1, le=100)):
    """Gain-based feature importance read directly from the active booster."""
    model = load_fraudshield()
    if not model:
        return {"available": False, "reason": "No active FraudShield model", "features": []}

    names = model.feature_order
    scores: Dict[str, float] = {}

    try:
        if model.model_type == "LightGBM":
            gains = model.model.feature_importance(importance_type="gain")
            booster_names = model.model.feature_name()
            for name, gain in zip(booster_names, gains):
                scores[name] = float(gain)
        else:
            scores = {k: float(v) for k, v in model.model.get_score(importance_type="gain").items()}
    except Exception as exc:
        return {"available": False, "reason": str(exc), "features": []}

    # Booster feature names can be positional (Column_0); map back to the spec order.
    remapped: Dict[str, float] = {}
    for key, value in scores.items():
        if key.startswith("Column_") and key[7:].isdigit():
            index = int(key[7:])
            key = names[index] if index < len(names) else key
        elif key.startswith("f") and key[1:].isdigit():
            index = int(key[1:])
            key = names[index] if index < len(names) else key
        remapped[key] = value

    total = sum(remapped.values()) or 1.0
    ranked = sorted(remapped.items(), key=lambda kv: -kv[1])[:top]

    return {
        "available": True,
        "model_version": model.version,
        "model_type": model.model_type,
        "importance_type": "gain",
        "features": [
            {"feature": name, "gain": round(gain, 2), "share": round(gain / total, 4)}
            for name, gain in ranked
        ],
    }


@router.get("/buffer")
async def buffer_browser(
    limit: int = Query(default=50, ge=1, le=500),
    outcome: Optional[str] = None,
    family: Optional[str] = None,
):
    """Adversarial buffer sample browser — the evidence Loop B trains on."""
    records = EvidenceBuffer().read_all()
    if outcome:
        records = [r for r in records if r.evasion_outcome == outcome]
    if family:
        records = [r for r in records if r.attack_family == family]

    recent = list(reversed(records[-limit:]))
    return {
        "stats": EvidenceBuffer().stats(),
        "records": [r.model_dump() for r in recent],
    }


@router.get("/comparison")
async def hardening_comparison(db: Session = Depends(get_db)):
    """Before/after hardening comparison for the most recent training round."""
    model_dir = Path(get_model_status()["spec_path"]).parent
    report_path = model_dir / "hardening_report.json"

    stored: Dict[str, Any] = {}
    if report_path.exists():
        try:
            stored = json.loads(report_path.read_text())
        except json.JSONDecodeError:
            stored = {}

    latest = db.query(ModelVersion).order_by(desc(ModelVersion.trained_at)).first()
    comparison: Dict[str, Any] = {}
    if latest:
        try:
            comparison = json.loads(latest.report_json).get("comparison", {})
        except json.JSONDecodeError:
            comparison = {}

    return {
        "hardening_report": stored,
        "comparison": comparison,
        "latest_version": latest.version if latest else None,
        "trained_at": latest.trained_at if latest else None,
    }
