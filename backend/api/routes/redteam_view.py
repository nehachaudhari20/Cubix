"""Red Team HTML-like view API — structured campaign data matching the HTML layout."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.knowledge.loader import KnowledgeLoader
from backend.platform.database import SessionLocal
from backend.platform.models import LoopRun, CampaignEvent

router = APIRouter(prefix="/api/redteam/view", tags=["Red Team View"])

# Pre-load KB
_kb: Optional[KnowledgeLoader] = None


def _get_kb() -> KnowledgeLoader:
    global _kb
    if _kb is None:
        _kb = KnowledgeLoader()
    return _kb


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CampaignStep(BaseModel):
    title: str
    description: str


class CampaignMemory(BaseModel):
    text: str
    confidence: float


class CampaignPayload(BaseModel):
    campaign_id: str
    step_id: int
    action: str
    customer_id: str
    device_id: Optional[str] = None
    merchant_id: Optional[str] = None
    beneficiary_id: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "INR"
    rail: str = "UPI"
    channel: str = "web"


class CampaignEntry(BaseModel):
    id: str
    family: str
    family_name: str
    status: str  # RUNNING | BLOCKED | SUCCEEDED | ANALYZING
    novelty: float
    stage: str
    step: str  # e.g. "6/9"
    hypothesis: str
    families_tags: List[str]
    plan: List[CampaignStep]
    payload: Dict[str, Any]
    memory: List[CampaignMemory]


class RedTeamViewResponse(BaseModel):
    campaigns: List[CampaignEntry]
    total_events: int
    total_families: int
    blocked_count: int
    bypassed_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _determine_status(events: List[dict]) -> str:
    """Determine campaign status from events."""
    if not events:
        return "RUNNING"
    decisions = [e.get("sandbox_decision", "") for e in events]
    if all(d == "BLOCK" for d in decisions):
        return "BLOCKED"
    if any(d == "ALLOW" for d in decisions):
        return "SUCCEEDED"
    return "ANALYZING"


def _build_hypothesis(family_detail: dict, family_id: str) -> str:
    """Build hypothesis text from KB family data."""
    if not family_detail:
        return f"Exploring {family_id} attack surface — testing detection controls against adversarial simulation strategy."

    name = family_detail.get("name", family_id)
    stage = family_detail.get("lifecycle_stage", "unknown")
    sim_type = family_detail.get("simulation_type", "unknown")
    variants = family_detail.get("variants", [])
    signals = family_detail.get("detection_signals", [])
    flow = family_detail.get("attack_flow", [])

    parts = [f"**{name}** — {stage} lifecycle stage."]
    if flow:
        parts.append(f"Attack flow: {flow[0]}.")
    if variants:
        parts.append(f"Testing {len(variants)} variant(s).")
    if signals:
        parts.append(f"{len(signals)} detection signal(s) mapped.")
    parts.append(f"Simulation type: {sim_type}.")

    return " ".join(parts)


def _build_plan(family_detail: dict, events: List[dict]) -> List[CampaignStep]:
    """Build plan steps from KB attack flow + events."""
    steps = []

    # From KB attack flow
    flow = family_detail.get("attack_flow", []) if family_detail else []
    for i, step_text in enumerate(flow[:6]):
        steps.append(CampaignStep(
            title=f"Step {i+1}",
            description=step_text,
        ))

    # From events if no KB flow
    if not steps and events:
        for i, evt in enumerate(events[:6]):
            steps.append(CampaignStep(
                title=f"Action {i+1}: {evt.get('family_name', 'unknown')}",
                description=f"Sandbox decision: {evt.get('sandbox_decision', '?')} | ML score: {evt.get('ml_score', 0):.3f} | Amount: ₹{evt.get('amount', 0):,.0f}",
            ))

    # Fallback
    if not steps:
        steps = [
            CampaignStep(title="Reconnaissance", description="Study target system behavior and detection rules."),
            CampaignStep(title="Payload generation", description="Create adversarial transaction patterns."),
            CampaignStep(title="Execution", description="Submit payloads to sandbox environment."),
            CampaignStep(title="Observe outcome", description="Record ALLOW/BLOCK decision and control triggers."),
        ]

    return steps


def _build_memory(family_detail: dict) -> List[CampaignMemory]:
    """Build memory entries from KB detection signals."""
    memories = []
    signals = family_detail.get("detection_signals", []) if family_detail else []

    for sig in signals[:6]:
        if isinstance(sig, dict):
            text = sig.get("name", sig.get("signal_id", str(sig)))
            method = sig.get("detection_method", "")
            if method:
                text += f" — detected via {method}"
        else:
            text = str(sig)
        memories.append(CampaignMemory(
            text=text,
            confidence=round(0.7 + random.random() * 0.25, 2),
        ))

    if not memories:
        memories = [
            CampaignMemory(text="No signal data available for this family.", confidence=0.0),
        ]

    return memories


def _build_payload(entry_id: str, events: List[dict], step_num: int) -> Dict[str, Any]:
    """Build payload from the latest event."""
    if events:
        last = events[-1]
        return {
            "campaign_id": entry_id[:8],
            "step_id": last.get("step", step_num),
            "action": last.get("family_name", "payment"),
            "customer_id": f"C{random.randint(1000,9999)}",
            "device_id": f"D{random.randint(1000,9999)}",
            "merchant_id": f"M{random.randint(1000,9999)}",
            "beneficiary_id": f"B{random.randint(1000,9999)}",
            "amount": last.get("amount", 5000),
            "currency": "INR",
            "rail": last.get("features", {}).get("payment_rail", "UPI"),
            "channel": "web",
        }
    return {
        "campaign_id": entry_id[:8],
        "step_id": step_num,
        "action": "payment",
        "customer_id": f"C{random.randint(1000,9999)}",
        "amount": 5000,
        "currency": "INR",
        "rail": "UPI",
        "channel": "web",
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/{run_id}")
async def get_redteam_view(run_id: str, db: Session = Depends(get_db)):
    """Return structured Red Team data matching the HTML layout."""
    run = db.get(LoopRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    kb = _get_kb()

    # Query events from the campaign_events table
    event_rows = db.query(CampaignEvent).filter(CampaignEvent.loop_run_id == run_id).all()
    events = []
    for e in event_rows:
        events.append({
            "id": e.id,
            "loop_run_id": e.loop_run_id,
            "family_id": e.family_id,
            "family_name": e.family_name,
            "step": e.step,
            "sandbox_decision": e.sandbox_decision,
            "evasion_outcome": e.evasion_outcome,
            "ml_score": e.ml_score,
            "amount": e.amount,
        })

    # Group events by family
    family_groups: Dict[str, List[dict]] = {}
    for evt in events:
        fid = evt.get("family_id", "unknown")
        family_groups.setdefault(fid, []).append(evt)

    # Build campaign entries
    campaigns: List[CampaignEntry] = []
    for fid, fam_events in family_groups.items():
        family_detail = kb.get_family(fid) if kb else None
        status = _determine_status(fam_events)
        total_steps = max(e.get("step", 1) for e in fam_events) if fam_events else 1
        current_step = fam_events[-1].get("step", total_steps) if fam_events else total_steps

        campaigns.append(CampaignEntry(
            id=fam_events[0].get("loop_run_id", run_id)[:12],
            family=fid,
            family_name=fam_events[0].get("family_name", fid),
            status=status,
            novelty=round(0.5 + random.random() * 0.45, 2),
            stage=family_detail.get("lifecycle_stage", "Payment") if family_detail else "Payment",
            step=f"{current_step}/{total_steps}",
            hypothesis=_build_hypothesis(family_detail, fid),
            families_tags=[fid] + (family_detail.get("controls_targeted", [])[:2] if family_detail else []),
            plan=_build_plan(family_detail, fam_events),
            payload=_build_payload(fid, fam_events, current_step),
            memory=_build_memory(family_detail),
        ))

    # Sort by event count descending
    campaigns.sort(key=lambda c: len([e for e in events if e.get("family_id") == c.family]), reverse=True)

    total_events = len(events)
    bypassed = sum(1 for e in events if e.get("evasion_outcome") == "bypassed")
    blocked = total_events - bypassed

    return RedTeamViewResponse(
        campaigns=campaigns,
        total_events=total_events,
        total_families=len(family_groups),
        blocked_count=blocked,
        bypassed_count=bypassed,
    )
