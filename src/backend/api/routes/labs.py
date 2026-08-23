"""
Labs API — control gap findings and counterfactual replay.

A control gap is not a single blocked transaction. It is a journey that
succeeded while every individual control reported that it was satisfied,
which points at a missing correlation rather than a mistuned threshold.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.platform.database import SessionLocal
from backend.platform.models import Campaign, Observation
from backend.sandbox.rules.control_registry import EXECUTABLE_DEFAULTS

router = APIRouter(prefix="/api/labs", tags=["Labs"])

# Candidate interventions offered per gap type: control key, and the change
# that would plausibly close the gap. Thresholds are synthetic and configurable.
INTERVENTIONS: Dict[str, List[Dict[str, Any]]] = {
    "silent_bypass": [
        {
            "name": "Tighten authorization allow threshold",
            "overrides": {"allow_threshold": 0.20},
            "rationale": "Route mid-risk journeys to step-up instead of straight-through allow.",
            "friction": "medium",
        },
        {
            "name": "Raise new-beneficiary risk contribution",
            "overrides": {"new_beneficiary_risk": 0.50},
            "rationale": "Novel payees carry more weight when combined with amount escalation.",
            "friction": "low",
        },
    ],
    "amount_escalation": [
        {
            "name": "Lower tier-1 amount limit",
            "overrides": {"amount_limit_tier1": 15000, "amount_tier1_risk": 0.35},
            "rationale": "Escalating amounts inside one journey should accumulate risk earlier.",
            "friction": "medium",
        },
        {
            "name": "Tighten structuring band",
            "overrides": {"structuring_min_amount": 15000, "structuring_count_threshold": 2},
            "rationale": "Catch just-below-threshold sequencing with fewer observations.",
            "friction": "high",
        },
    ],
    "velocity_evasion": [
        {
            "name": "Reduce 24h velocity limit",
            "overrides": {"velocity_limit_24h": 3, "velocity_tier1_risk": 0.35},
            "rationale": "Burst activity is currently absorbed under the existing limit.",
            "friction": "high",
        },
    ],
    "ml_underscore": [
        {
            "name": "Lower challenge threshold",
            "overrides": {"challenge_threshold": 0.45},
            "rationale": "FraudShield ranks these low; widen the step-up band while retraining.",
            "friction": "medium",
        },
    ],
}


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


def _classify_gap(o: Observation) -> str:
    """Attribute a bypassed payment to the weakest control surface."""
    triggers = _loads(o.control_triggers_json, [])
    ml = o.ml_score or 0.0

    if not triggers:
        return "silent_bypass"
    if (o.amount or 0) >= 20000 and not any("amount" in t or "aml" in t for t in triggers):
        return "amount_escalation"
    if not any("velocity" in t for t in triggers):
        return "velocity_evasion"
    if ml < 0.4:
        return "ml_underscore"
    return "silent_bypass"


GAP_TITLES = {
    "silent_bypass": "Journey allowed with no control objection",
    "amount_escalation": "Amount escalation not correlated across the journey",
    "velocity_evasion": "Velocity limits absorbed the attack burst",
    "ml_underscore": "FraudShield scored the attack as low risk",
}

GAP_DESCRIPTIONS = {
    "silent_bypass": (
        "Every control that ran reported no objection, yet the payment was adversarial. "
        "This is the signature of a missing journey-level correlation rather than a "
        "mistuned individual threshold."
    ),
    "amount_escalation": (
        "Amounts rose across the campaign but each step was evaluated in isolation, so no "
        "single amount rule fired."
    ),
    "velocity_evasion": (
        "The campaign stayed inside the configured velocity window, so burst detection "
        "never contributed risk."
    ),
    "ml_underscore": (
        "Rules were satisfied and FraudShield returned a low probability, so unified risk "
        "stayed under the allow threshold."
    ),
}


@router.get("/gaps")
async def control_gaps(db: Session = Depends(get_db)):
    """Aggregate bypassed journeys into systemic control gap findings."""
    bypassed = (
        db.query(Observation)
        .filter(Observation.evasion_outcome == "bypassed")
        .filter(Observation.action_type == "initiate_payment")
        .all()
    )

    grouped: Dict[str, List[Observation]] = {}
    for o in bypassed:
        grouped.setdefault(_classify_gap(o), []).append(o)

    findings = []
    for gap_type, rows in grouped.items():
        amounts = [r.amount for r in rows if r.amount is not None]
        ml_scores = [r.ml_score for r in rows if r.ml_score is not None]
        families = sorted({r.family_id for r in rows})

        findings.append({
            "gap_id": gap_type,
            "title": GAP_TITLES.get(gap_type, gap_type),
            "description": GAP_DESCRIPTIONS.get(gap_type, ""),
            "severity": "high" if len(rows) >= 5 else "medium" if len(rows) >= 2 else "low",
            "occurrences": len(rows),
            "affected_families": families,
            "avg_amount": round(sum(amounts) / len(amounts), 2) if amounts else None,
            "avg_ml_score": round(sum(ml_scores) / len(ml_scores), 4) if ml_scores else None,
            "interventions": INTERVENTIONS.get(gap_type, []),
            "evidence": [
                {
                    "observation_id": r.id,
                    "campaign_id": r.campaign_id,
                    "family_id": r.family_id,
                    "family_name": r.family_name,
                    "step": r.step,
                    "amount": r.amount,
                    "ml_score": r.ml_score,
                    "rule_risk": r.rule_risk,
                    "risk_score": r.risk_score,
                    "decision": r.decision,
                    "control_triggers": _loads(r.control_triggers_json, []),
                }
                for r in sorted(rows, key=lambda x: -(x.amount or 0))[:10]
            ],
        })

    findings.sort(key=lambda f: -f["occurrences"])
    return {
        "total_bypassed": len(bypassed),
        "findings": findings,
        "control_registry": EXECUTABLE_DEFAULTS,
    }


class CounterfactualRequest(BaseModel):
    observation_id: str
    overrides: Dict[str, Any] = Field(default_factory=dict)


@router.post("/counterfactual")
async def counterfactual_replay(req: CounterfactualRequest, db: Session = Depends(get_db)):
    """
    Replay the campaign that produced this observation under changed controls.

    The whole campaign is replayed, not just the single action, because the
    attack's success depends on accumulated state.
    """
    target = db.get(Observation, req.observation_id)
    if not target:
        raise HTTPException(status_code=404, detail="Observation not found")
    if not req.overrides:
        raise HTTPException(status_code=400, detail="At least one control override is required")

    campaign = db.get(Campaign, target.campaign_id)
    payloads = _loads(campaign.payloads_json, []) if campaign else []
    if not payloads:
        raise HTTPException(status_code=409, detail="Campaign payloads unavailable for replay")

    from backend.red_team.sandbox_client import SandboxClient
    from backend.sandbox.rules.base import BaseRule

    def replay() -> List[Dict[str, Any]]:
        client = SandboxClient()
        results = []
        for payload in payloads:
            response = client.execute_payload(payload)
            state = response.get("state") or {}
            results.append({
                "step": payload.get("step"),
                "action_type": payload.get("action_type"),
                "decision": response.get("decision"),
                "reason": response.get("reason"),
                "ml_score": state.get("ml_score"),
                "rule_risk": state.get("rule_risk"),
                "risk_score": state.get("risk_score"),
                "control_triggers": response.get("control_triggers") or [],
                "amount": (payload.get("action_payload") or {}).get("amount"),
            })
        return results

    BaseRule.clear_overrides()
    try:
        control_run = replay()
        BaseRule.set_overrides(req.overrides)
        variant_run = replay()
    finally:
        BaseRule.clear_overrides()

    def payment_steps(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [r for r in rows if r["action_type"] == "initiate_payment"]

    base_payments = payment_steps(control_run)
    new_payments = payment_steps(variant_run)

    base_allowed = sum(1 for r in base_payments if r["decision"] == "ALLOW")
    new_allowed = sum(1 for r in new_payments if r["decision"] == "ALLOW")
    new_challenged = sum(1 for r in new_payments if r["decision"] == "CHALLENGE")

    prevented = base_allowed - new_allowed
    prevention_rate = round(prevented / base_allowed, 4) if base_allowed else 0.0
    friction_rate = round(new_challenged / len(new_payments), 4) if new_payments else 0.0

    return {
        "observation_id": req.observation_id,
        "campaign_id": target.campaign_id,
        "family_id": target.family_id,
        "family_name": target.family_name,
        "overrides": req.overrides,
        "baseline": {
            "payments": len(base_payments),
            "allowed": base_allowed,
            "steps": base_payments,
        },
        "counterfactual": {
            "payments": len(new_payments),
            "allowed": new_allowed,
            "challenged": new_challenged,
            "steps": new_payments,
        },
        "outcome": {
            "attacks_prevented": prevented,
            "prevention_rate": prevention_rate,
            "added_friction_rate": friction_rate,
            "verdict": (
                "prevents the attack" if prevented > 0
                else "no change in outcome"
            ),
        },
        "note": "Thresholds are synthetic sandbox policy, not production payment rules.",
    }
