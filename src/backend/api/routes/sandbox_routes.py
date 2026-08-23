"""Sandbox API — observation contracts rendered as inspectable journeys."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.platform.database import SessionLocal
from backend.platform.journey import diff_snapshots
from backend.platform.models import Observation

router = APIRouter(prefix="/api/sandbox", tags=["Sandbox"])

# Which engine owns each journey step reported by the orchestrator.
# Keys are normalized (lowercase, underscores) before lookup.
ENGINE_BY_STEP = {
    "payment_initiation": "Payment Initiation",
    "risk_scoring": "Risk",
    "risk": "Risk",
    "authorization": "Authorization",
    "authorisation": "Authorization",
    "settlement": "Settlement / Post-payment",
    "post_payment": "Settlement / Post-payment",
    "kyc": "Identity / KYC",
    "kyc_verification": "Identity / KYC",
    "identity": "Identity / KYC",
    "customer_registration": "Identity / KYC",
    "device": "Device / Session",
    "device_registration": "Device / Session",
    "session": "Device / Session",
    "authentication": "Authentication",
    "auth": "Authentication",
    "account_opening": "Account / Merchant",
    "open_account": "Account / Merchant",
    "merchant_onboarding": "Account / Merchant",
    "merchant": "Account / Merchant",
    "beneficiary_link": "Account / Merchant",
    "beneficiary": "Account / Merchant",
}


def _engine_for(step_name: str) -> str:
    key = step_name.strip().lower().replace(" ", "_").replace("/", "_")
    if key in ENGINE_BY_STEP:
        return ENGINE_BY_STEP[key]
    for alias, engine in ENGINE_BY_STEP.items():
        if alias in key:
            return engine
    return "Orchestrator"


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


def _step_passed(result: Any) -> bool:
    """Engines report their outcome under different keys; treat any of them as failure."""
    if not isinstance(result, dict):
        return True
    for key in ("passed", "valid", "success", "verified"):
        if key in result and result[key] is False:
            return False
    if str(result.get("status", "")).upper() in ("FAIL", "FAILED", "BLOCK", "BLOCKED"):
        return False
    if str(result.get("decision", "")).upper() in ("BLOCK", "FAIL"):
        return False
    return True


def _summary(o: Observation) -> Dict[str, Any]:
    return {
        "id": o.id,
        "campaign_id": o.campaign_id,
        "loop_run_id": o.loop_run_id,
        "family_id": o.family_id,
        "family_name": o.family_name,
        "transaction_id": o.transaction_id,
        "step": o.step,
        "action_type": o.action_type,
        "decision": o.decision,
        "reason": o.reason,
        "evasion_outcome": o.evasion_outcome,
        "ml_score": o.ml_score,
        "rule_risk": o.rule_risk,
        "risk_score": o.risk_score,
        "amount": o.amount,
        "payment_rail": o.payment_rail,
        "location_region": o.location_region,
        "control_triggers": _loads(o.control_triggers_json, []),
        "created_at": o.created_at,
    }


@router.get("/observations")
async def list_observations(
    limit: int = Query(default=100, ge=1, le=1000),
    decision: Optional[str] = None,
    action_type: Optional[str] = None,
    family_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Browsable list of every action executed against the payment environment."""
    query = db.query(Observation)
    if decision:
        query = query.filter(Observation.decision == decision)
    if action_type:
        query = query.filter(Observation.action_type == action_type)
    if family_id:
        query = query.filter(Observation.family_id == family_id)
    if campaign_id:
        query = query.filter(Observation.campaign_id == campaign_id)
    rows = query.order_by(desc(Observation.created_at)).limit(limit).all()
    return [_summary(o) for o in rows]


@router.get("/observations/{observation_id}")
async def get_observation(observation_id: str, db: Session = Depends(get_db)):
    """The full observation contract for one action, shaped for a timeline view."""
    o = db.get(Observation, observation_id)
    if not o:
        raise HTTPException(status_code=404, detail="Observation not found")

    journey = _loads(o.journey_json, [])
    state_before = _loads(o.state_before_json, {})
    state_after = _loads(o.state_after_json, {})

    timeline: List[Dict[str, Any]] = []
    for entry in journey:
        step_name = entry.get("step", "") if isinstance(entry, dict) else str(entry)
        result = entry.get("result", {}) if isinstance(entry, dict) else {}
        timeline.append({
            "step": step_name,
            "engine": _engine_for(step_name),
            "result": result,
            "passed": _step_passed(result),
        })

    detail = _summary(o)
    detail.update({
        "target_control": o.target_control,
        "expected_outcome": o.expected_outcome,
        "blocking_control": o.blocking_control,
        "timeline": timeline,
        "state_before": state_before,
        "state_after": state_after,
        "state_changes": diff_snapshots(state_before, state_after),
        "payload": _loads(o.payload_json, {}),
        "features": _loads(o.features_json, {}),
        "analysis": _loads(o.analysis_json, {}),
    })
    return detail


@router.get("/stats")
async def sandbox_stats(db: Session = Depends(get_db)):
    """Decision mix and control trigger frequency across all executed actions."""
    rows = db.query(Observation).all()

    decisions: Dict[str, int] = {}
    actions: Dict[str, int] = {}
    controls: Dict[str, int] = {}
    for o in rows:
        decisions[o.decision] = decisions.get(o.decision, 0) + 1
        actions[o.action_type] = actions.get(o.action_type, 0) + 1
        for control in _loads(o.control_triggers_json, []):
            controls[control] = controls.get(control, 0) + 1

    return {
        "total_actions": len(rows),
        "decisions": decisions,
        "action_types": actions,
        "top_controls": sorted(
            ({"control": k, "count": v} for k, v in controls.items()),
            key=lambda x: -x["count"],
        )[:15],
    }
