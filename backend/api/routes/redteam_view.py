"""Red Team Campaign Replay API — rich loop + KB data for judge deep-dive."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.knowledge.loader import KnowledgeLoader
from backend.platform.database import SessionLocal
from backend.platform.models import CampaignEvent, LoopRun

router = APIRouter(prefix="/api/redteam/view", tags=["Red Team View"])

EVAL_DIR = Path(__file__).resolve().parents[3] / "data" / "evaluation"

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


class CampaignStep(BaseModel):
    title: str
    description: str
    decision: Optional[str] = None
    ml_score: Optional[float] = None
    amount: Optional[float] = None
    outcome: Optional[str] = None


class CampaignMemory(BaseModel):
    text: str
    confidence: float
    source: str = "kb"
    kind: str = "signal"


class ThreatIntelligence(BaseModel):
    summary: str
    objective: Optional[str] = None
    attacker: Optional[str] = None
    target: Optional[str] = None
    surface: Optional[str] = None
    simulation_type: Optional[str] = None
    genai_classification: Optional[str] = None
    evidence_confidence: Optional[str] = None
    prerequisites: List[str] = Field(default_factory=list)
    attack_flow: List[str] = Field(default_factory=list)
    variants: List[str] = Field(default_factory=list)
    controls_targeted: List[str] = Field(default_factory=list)
    signals: List[Dict[str, Any]] = Field(default_factory=list)
    technique_ids: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None


class CampaignEntry(BaseModel):
    id: str
    family: str
    family_name: str
    status: str
    executed: bool = False
    novelty: float
    stage: str
    step: str
    event_count: int = 0
    blocked: int = 0
    bypassed: int = 0
    challenged: int = 0
    mean_ml_score: Optional[float] = None
    hypothesis: str  # short summary for chips / list
    threat_intelligence: ThreatIntelligence
    families_tags: List[str]
    plan: List[CampaignStep]
    payload: Dict[str, Any]
    payloads: List[Dict[str, Any]] = Field(default_factory=list)
    memory: List[CampaignMemory]
    events: List[Dict[str, Any]] = Field(default_factory=list)


class RedTeamViewResponse(BaseModel):
    loop_id: str
    loop_status: str
    families_tested: int
    campaigns: List[CampaignEntry]
    total_events: int
    total_families: int
    executed_families: int
    blocked_count: int
    bypassed_count: int
    buffer_payments: int = 0
    score_lift: Optional[float] = None
    kb_family_count: int = 0


def _load_eval(run_id: str) -> Dict[str, Any]:
    path = EVAL_DIR / f"loop_{run_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _load_failure(run_id: str) -> Dict[str, Any]:
    path = EVAL_DIR / f"failure_analysis_{run_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _novelty(family_detail: Optional[dict], fam_events: List[dict], asr_row: Optional[dict]) -> float:
    if asr_row and asr_row.get("novelty_score") is not None:
        try:
            return round(float(asr_row["novelty_score"]), 3)
        except (TypeError, ValueError):
            pass
    score = 0.45
    if family_detail:
        genai = family_detail.get("genai") or {}
        if family_detail.get("genai_load_bearing") or genai.get("load_bearing"):
            score += 0.2
        sim = (family_detail.get("simulation_type") or "").lower()
        if "hybrid" in sim or "composite" in sim:
            score += 0.12
        if len(family_detail.get("variants") or []) >= 3:
            score += 0.05
    if fam_events:
        bypass = sum(1 for e in fam_events if (e.get("evasion_outcome") or "").lower() in ("bypassed", "bypass", "allow"))
        allow = sum(1 for e in fam_events if (e.get("sandbox_decision") or "").upper() == "ALLOW")
        rate = (bypass + allow) / max(len(fam_events), 1)
        score += min(0.25, rate * 0.3)
    return round(min(0.98, score), 3)


def _status(fam_events: List[dict], executed: bool) -> str:
    if not executed:
        return "NOT_RUN"
    if not fam_events:
        return "RUNNING"
    decisions = [(e.get("sandbox_decision") or "").upper() for e in fam_events]
    if any(d == "ALLOW" for d in decisions):
        return "SUCCEEDED"
    if all(d == "BLOCK" for d in decisions if d):
        return "BLOCKED"
    if any(d == "CHALLENGE" for d in decisions):
        return "CHALLENGED"
    return "ANALYZING"


def _threat_intel(family_detail: Optional[dict], family_id: str, fam_events: List[dict]) -> ThreatIntelligence:
    if not family_detail:
        return ThreatIntelligence(
            summary=f"Family {family_id} — limited KB metadata available.",
            reasoning=f"Exploring {family_id} attack surface against sandbox controls.",
        )

    name = family_detail.get("name") or family_id
    stage = family_detail.get("lifecycle_stage") or "unknown"
    sim = family_detail.get("simulation_type") or "unknown"
    flow = list(family_detail.get("attack_flow") or [])
    variants = list(family_detail.get("variants") or [])
    signals = list(family_detail.get("detection_signals") or [])
    controls = list(family_detail.get("controls_targeted") or [])
    prereq = list(family_detail.get("prerequisites") or [])
    objective = family_detail.get("objective")
    attacker = family_detail.get("attacker")
    target = family_detail.get("target")

    parts = [f"{name} — {stage} lifecycle."]
    if objective:
        parts.append(f"Objective: {objective}")
    if attacker:
        parts.append(f"Attacker model: {attacker}")
    if target:
        parts.append(f"Target: {target}")
    if flow:
        parts.append(f"Primary flow: {flow[0]}")
    parts.append(
        f"{len(variants)} variant(s), {len(signals)} mapped signal(s), "
        f"{len(controls)} control(s) targeted. Simulation: {sim}."
    )
    if fam_events:
        decisions = {}
        for e in fam_events:
            d = (e.get("sandbox_decision") or "?").upper()
            decisions[d] = decisions.get(d, 0) + 1
        parts.append(
            "Loop outcomes: " + ", ".join(f"{k}×{v}" for k, v in sorted(decisions.items()))
        )

    return ThreatIntelligence(
        summary=" ".join(parts),
        objective=objective,
        attacker=attacker,
        target=target,
        surface=family_detail.get("surface"),
        simulation_type=sim,
        genai_classification=family_detail.get("genai_classification"),
        evidence_confidence=family_detail.get("evidence_confidence"),
        prerequisites=prereq,
        attack_flow=flow,
        variants=[str(v) for v in variants],
        controls_targeted=[str(c) for c in controls],
        signals=[
            {
                "name": (s.get("name") if isinstance(s, dict) else str(s)),
                "signal_id": (s.get("signal_id") if isinstance(s, dict) else None),
                "detection_method": (s.get("detection_method") if isinstance(s, dict) else None),
            }
            for s in signals
        ],
        technique_ids=list(family_detail.get("technique_ids") or []),
        reasoning=family_detail.get("narrative") or family_detail.get("description"),
    )


def _build_plan(family_detail: Optional[dict], fam_events: List[dict]) -> List[CampaignStep]:
    steps: List[CampaignStep] = []
    flow = list((family_detail or {}).get("attack_flow") or [])

    # Merge KB flow with observed sandbox steps
    for i, text in enumerate(flow):
        match = fam_events[i] if i < len(fam_events) else None
        steps.append(
            CampaignStep(
                title=f"Flow {i + 1}",
                description=str(text),
                decision=(match or {}).get("sandbox_decision"),
                ml_score=(match or {}).get("ml_score"),
                amount=(match or {}).get("amount"),
                outcome=(match or {}).get("evasion_outcome"),
            )
        )

    # Extra observed steps beyond KB flow
    for i, evt in enumerate(fam_events[len(flow) :]):
        steps.append(
            CampaignStep(
                title=f"Observed step {(evt.get('step') or len(flow) + i + 1)}",
                description=(
                    f"{evt.get('family_name') or 'action'} · "
                    f"decision={evt.get('sandbox_decision')} · "
                    f"outcome={evt.get('evasion_outcome')}"
                ),
                decision=evt.get("sandbox_decision"),
                ml_score=evt.get("ml_score"),
                amount=evt.get("amount"),
                outcome=evt.get("evasion_outcome"),
            )
        )

    if not steps:
        prereq = list((family_detail or {}).get("prerequisites") or [])
        for i, p in enumerate(prereq[:4]):
            steps.append(CampaignStep(title=f"Prerequisite {i + 1}", description=str(p)))
        if not steps:
            steps = [
                CampaignStep(title="Reconnaissance", description="Map controls and signals for this family."),
                CampaignStep(title="Payload generation", description="Synthesize adversarial payment actions."),
                CampaignStep(title="Sandbox execution", description="Submit to FraudShield sandbox."),
                CampaignStep(title="Observe & memorize", description="Record ALLOW/BLOCK and control gaps."),
            ]
    return steps


def _build_memory(
    family_detail: Optional[dict],
    fam_events: List[dict],
    failure: Dict[str, Any],
    family_id: str,
) -> List[CampaignMemory]:
    memories: List[CampaignMemory] = []

    signals = list((family_detail or {}).get("detection_signals") or [])
    for sig in signals[:12]:
        if isinstance(sig, dict):
            text = sig.get("name") or sig.get("signal_id") or str(sig)
            method = sig.get("detection_method") or ""
            if method:
                text = f"{text} — {method}"
            sid = sig.get("signal_id") or ""
        else:
            text = str(sig)
            sid = ""
        memories.append(
            CampaignMemory(
                text=text,
                confidence=0.82 if sid else 0.7,
                source="kb_signal",
                kind="signal",
            )
        )

    for ctl in list((family_detail or {}).get("controls_targeted") or [])[:8]:
        memories.append(
            CampaignMemory(
                text=f"Control in scope: {ctl}",
                confidence=0.75,
                source="kb_control",
                kind="control",
            )
        )

    # Failure analysis / gap lab snippets for this family
    per_family = failure.get("per_family_asr") or failure.get("per_family") or []
    for row in per_family:
        fam = row.get("family") or row.get("family_id") or row.get("attack_family")
        if fam and fam != family_id and family_id not in str(fam):
            continue
        asr = row.get("asr_after") or row.get("asr") or row.get("bypass_rate")
        if asr is not None:
            memories.append(
                CampaignMemory(
                    text=f"Eval ASR for {fam or family_id}: {float(asr):.3f}",
                    confidence=0.9,
                    source="evaluation",
                    kind="asr",
                )
            )
        gaps = row.get("control_gaps") or row.get("missing_controls") or []
        if isinstance(gaps, list):
            for g in gaps[:6]:
                memories.append(
                    CampaignMemory(
                        text=f"Control gap: {g}",
                        confidence=0.88,
                        source="failure_analysis",
                        kind="gap",
                    )
                )

    gap_summary = failure.get("gap_summary") or {}
    for ctl in list(gap_summary.get("unique_missing_controls") or [])[:6]:
        memories.append(
            CampaignMemory(
                text=f"Loop-wide missing control: {ctl}",
                confidence=0.7,
                source="failure_analysis",
                kind="gap",
            )
        )

    # Outcome memory from events
    for e in fam_events[-8:]:
        memories.append(
            CampaignMemory(
                text=(
                    f"Step {e.get('step')}: {e.get('sandbox_decision')} / "
                    f"{e.get('evasion_outcome')} · ml={e.get('ml_score')} · amt={e.get('amount')}"
                ),
                confidence=0.95,
                source="campaign_event",
                kind="outcome",
            )
        )

    if not memories:
        memories.append(
            CampaignMemory(
                text="No memory entries yet — run a platform loop to populate outcomes.",
                confidence=0.0,
                source="system",
                kind="empty",
            )
        )
    return memories


def _evidence_for_family(buffer_rows: List[dict], family_id: str, family_name: str, run_id: str) -> List[dict]:
    out = []
    for r in buffer_rows:
        fam = r.get("attack_family") or ""
        camp = str(r.get("campaign_id") or "")
        if fam == family_id or fam == family_name or family_id in camp or run_id[:8] in camp:
            out.append(r)
    # Prefer family match
    exact = [r for r in buffer_rows if (r.get("attack_family") or "") in (family_id, family_name)]
    return exact or out


def _build_payloads(
    entry_id: str,
    fam_events: List[dict],
    evidence: List[dict],
    family_detail: Optional[dict],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    payloads: List[Dict[str, Any]] = []

    for r in evidence[:12]:
        feats = r.get("features") or {}
        payloads.append(
            {
                "source": "evidence_buffer",
                "evidence_id": r.get("evidence_id"),
                "campaign_id": r.get("campaign_id"),
                "attack_family": r.get("attack_family"),
                "action_type": r.get("action_type"),
                "sandbox_decision": r.get("sandbox_decision"),
                "evasion_outcome": r.get("evasion_outcome"),
                "ml_score": r.get("ml_score"),
                "amount": r.get("amount"),
                "step": r.get("step"),
                "control_triggers": r.get("control_triggers") or [],
                "blocking_control": r.get("blocking_control"),
                "features": feats if isinstance(feats, dict) else {},
                "timestamp": r.get("timestamp"),
            }
        )

    for e in fam_events[:12]:
        payloads.append(
            {
                "source": "campaign_event",
                "campaign_id": entry_id[:8],
                "family_id": e.get("family_id"),
                "family_name": e.get("family_name"),
                "step": e.get("step"),
                "sandbox_decision": e.get("sandbox_decision"),
                "evasion_outcome": e.get("evasion_outcome"),
                "ml_score": e.get("ml_score"),
                "amount": e.get("amount"),
            }
        )

    if not payloads and family_detail:
        payloads.append(
            {
                "source": "kb_template",
                "attack_id": family_detail.get("attack_id"),
                "simulation_type": family_detail.get("simulation_type"),
                "simulation_template_id": family_detail.get("simulation_template_id"),
                "surface": family_detail.get("surface"),
                "variants": (family_detail.get("variants") or [])[:5],
                "note": "No executed payload yet — template derived from KB.",
            }
        )

    primary = payloads[0] if payloads else {
        "campaign_id": entry_id[:8],
        "note": "No payload data",
    }
    return primary, payloads


def _family_asr_map(eval_data: Dict[str, Any], failure: Dict[str, Any]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for src in (
        eval_data.get("per_family") or [],
        eval_data.get("asr", {}).get("per_family") if isinstance(eval_data.get("asr"), dict) else [],
        failure.get("per_family_asr") or [],
        failure.get("per_family") or [],
    ):
        if not isinstance(src, list):
            continue
        for row in src:
            if not isinstance(row, dict):
                continue
            key = row.get("family") or row.get("family_id") or row.get("attack_family")
            if key:
                out[str(key)] = row
    return out


@router.get("/loops")
async def list_loops_for_redteam(limit: int = 30, db: Session = Depends(get_db)):
    """List platform loops for the Red Team loop selector."""
    runs = db.query(LoopRun).order_by(desc(LoopRun.started_at)).limit(limit).all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "families_count": r.families_count,
            "buffer_payments": r.buffer_payments,
            "buffer_blocked": r.buffer_blocked,
            "buffer_bypassed": r.buffer_bypassed,
            "score_lift": r.score_lift,
            "trigger": r.trigger,
        }
        for r in runs
    ]


@router.get("/{run_id}", response_model=RedTeamViewResponse)
async def get_redteam_view(run_id: str, limit: int = 20, db: Session = Depends(get_db)):
    """Structured Red Team deep-dive for a platform loop (up to `limit` campaigns)."""
    run = db.get(LoopRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Loop not found")

    kb = _get_kb()
    eval_data = _load_eval(run_id)
    failure = _load_failure(run_id)
    asr_map = _family_asr_map(eval_data, failure)

    event_rows = (
        db.query(CampaignEvent)
        .filter(CampaignEvent.loop_run_id == run_id)
        .order_by(CampaignEvent.created_at.asc())
        .all()
    )
    events: List[dict] = []
    for e in event_rows:
        events.append(
            {
                "id": e.id,
                "loop_run_id": e.loop_run_id,
                "family_id": e.family_id,
                "family_name": e.family_name,
                "step": e.step,
                "sandbox_decision": e.sandbox_decision,
                "evasion_outcome": e.evasion_outcome,
                "ml_score": e.ml_score,
                "amount": e.amount,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
        )

    family_groups: Dict[str, List[dict]] = {}
    for evt in events:
        fid = evt.get("family_id") or "unknown"
        family_groups.setdefault(fid, []).append(evt)

    # Evidence buffer (may include records from this loop)
    try:
        raw = EvidenceBuffer().read_all()
        buffer_rows = []
        for r in raw[-500:]:
            d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
            buffer_rows.append(d)
    except Exception:
        buffer_rows = []

    campaigns: List[CampaignEntry] = []
    executed_ids = list(family_groups.keys())

    def _build_entry(fid: str, fam_events: List[dict], executed: bool) -> CampaignEntry:
        family_detail = kb.get_family(fid) if kb else None
        name = (
            (fam_events[0].get("family_name") if fam_events else None)
            or (family_detail or {}).get("name")
            or fid
        )
        status = _status(fam_events, executed)
        total_steps = max((e.get("step") or 1) for e in fam_events) if fam_events else max(len((family_detail or {}).get("attack_flow") or []), 1)
        current_step = fam_events[-1].get("step", total_steps) if fam_events else 0
        blocked = sum(1 for e in fam_events if (e.get("sandbox_decision") or "").upper() == "BLOCK")
        challenged = sum(1 for e in fam_events if (e.get("sandbox_decision") or "").upper() == "CHALLENGE")
        bypassed = sum(
            1
            for e in fam_events
            if (e.get("evasion_outcome") or "").lower() in ("bypassed", "bypass")
            or (e.get("sandbox_decision") or "").upper() == "ALLOW"
        )
        scores = [e.get("ml_score") for e in fam_events if e.get("ml_score") is not None]
        mean_ml = round(sum(scores) / len(scores), 4) if scores else None
        ti = _threat_intel(family_detail, fid, fam_events)
        evidence = _evidence_for_family(buffer_rows, fid, name, run_id)
        primary_payload, payloads = _build_payloads(fid, fam_events, evidence, family_detail)
        tags = [fid]
        if family_detail:
            tags += list(family_detail.get("controls_targeted") or [])[:3]
            if family_detail.get("surface"):
                tags.append(str(family_detail["surface"]))
        return CampaignEntry(
            id=f"{run_id[:8]}-{fid}",
            family=fid,
            family_name=name,
            status=status,
            executed=executed,
            novelty=_novelty(family_detail, fam_events, asr_map.get(fid) or asr_map.get(name)),
            stage=(family_detail or {}).get("lifecycle_stage") or "Payment",
            step=f"{current_step}/{total_steps}" if executed else f"0/{total_steps}",
            event_count=len(fam_events),
            blocked=blocked,
            bypassed=bypassed,
            challenged=challenged,
            mean_ml_score=mean_ml,
            hypothesis=ti.summary,
            threat_intelligence=ti,
            families_tags=tags,
            plan=_build_plan(family_detail, fam_events),
            payload=primary_payload,
            payloads=payloads,
            memory=_build_memory(family_detail, fam_events, failure, fid),
            events=fam_events[-20:],
        )

    # Executed campaigns first (by event volume)
    for fid, fam_events in sorted(family_groups.items(), key=lambda kv: len(kv[1]), reverse=True):
        campaigns.append(_build_entry(fid, fam_events, executed=True))

    # Pad to `limit` with rich KB families not yet in this loop
    target = max(1, min(limit, 40))
    if len(campaigns) < target and kb:
        for fam in kb.families:
            if len(campaigns) >= target:
                break
            fid = fam.get("attack_id")
            if not fid or fid in executed_ids:
                continue
            campaigns.append(_build_entry(fid, [], executed=False))

    total_events = len(events)
    bypassed_count = sum(
        1
        for e in events
        if (e.get("evasion_outcome") or "").lower() in ("bypassed", "bypass")
        or (e.get("sandbox_decision") or "").upper() == "ALLOW"
    )
    blocked_count = sum(1 for e in events if (e.get("sandbox_decision") or "").upper() == "BLOCK")

    return RedTeamViewResponse(
        loop_id=run_id,
        loop_status=run.status,
        families_tested=run.families_count or len(executed_ids),
        campaigns=campaigns,
        total_events=total_events,
        total_families=len(campaigns),
        executed_families=len(executed_ids),
        blocked_count=blocked_count,
        bypassed_count=bypassed_count,
        buffer_payments=run.buffer_payments or 0,
        score_lift=run.score_lift,
        kb_family_count=len(kb.families) if kb else 0,
    )
