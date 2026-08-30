"""Red Team Campaign API — campaigns, timeline, safety, memory, strategy."""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.safety.policy_engine import SimulationPolicyEngine

router = APIRouter(prefix="/api/v1/red-team", tags=["red-team-campaign"])

_campaign_store: Dict[str, Dict[str, Any]] = {}
_safety_engine = SimulationPolicyEngine()
_lock = threading.Lock()


class CampaignCreateRequest(BaseModel):
    attack_family: str
    composite_families: List[str] = Field(default_factory=list)
    strategy: str = "sequential"
    campaign_size: int = 20
    mutation_budget: int = 2
    max_events: int = 250
    execute: bool = True


class HypothesisRequest(BaseModel):
    tested_families: List[str] = Field(default_factory=list)
    max_hypotheses: int = 12
    prefer_composites: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_agent(campaign_id: str, agent: str, status: str, detail: Optional[str] = None) -> None:
    with _lock:
        c = _campaign_store.get(campaign_id)
        if not c:
            return
        for step in c["timeline"]:
            if step["agent"] == agent:
                step["status"] = status
                if detail:
                    step["detail"] = detail
                step["updated_at"] = _now()
                break
        c["updated_at"] = _now()


def _execute_campaign(campaign_id: str) -> None:
    """Run Threat Hunter → Planner → Generator → Sandbox for one family."""
    try:
        from backend.red_team.agent_helpers import OfflineKnowledge
        from backend.red_team.agents.threat_hunter import ThreatHunter
        from backend.red_team.agents.attack_planner import AttackPlanner
        from backend.red_team.agents.attack_generator import AttackGenerator
        from backend.red_team.agents.failure_analyzer import FailureAnalyzer
        from backend.red_team.agents.memory_agent import MemoryAgent
        from backend.red_team.agents.strategy_layer import StrategyLayer
        from backend.red_team.deepteam.linear_mutator import LinearMutator
        from backend.red_team.runner import run_hypothesis_campaign
        from backend.red_team.sandbox_client import SandboxClient
        from backend.red_team.schemas import Hypothesis

        with _lock:
            c = _campaign_store.get(campaign_id)
            if not c:
                return
            c["status"] = "running"
            family_id = c["attack_family"]
            composites = list(c.get("composite_families") or [])
            strategy = c.get("strategy") or "kb"

        kb = OfflineKnowledge()
        family = kb.get_family(family_id)
        if not family:
            with _lock:
                c = _campaign_store[campaign_id]
                c["status"] = "failed"
                c["error"] = f"Unknown family {family_id}"
            return

        hunter = ThreatHunter()
        planner = AttackPlanner()
        generator = AttackGenerator()
        analyzer = FailureAnalyzer()
        mutator = LinearMutator()
        memory = MemoryAgent()
        strategy_layer = StrategyLayer(memory)
        client = SandboxClient()

        # 1. Threat Hunter
        _set_agent(campaign_id, "Threat Hunter", "running")
        if composites:
            hypothesis = Hypothesis(
                name=f"Campaign {family_id} + {composites}",
                primary_family=family_id,
                composite_families=composites,
                target_stages=[family.get("lifecycle_stage") or "Payment Initiation"],
                novelty_score=0.8,
                success_probability=0.5,
                prerequisites=list(family.get("prerequisites") or [])[:4],
                attack_flow_summary=" || ".join(
                    (family.get("attack_flow") or [family.get("name") or family_id])[:4]
                ),
                reasoning=f"Campaign Lab launch: {family_id}",
                suggested_variant=(family.get("variants") or ["default"])[0],
                jailbreak_strategy=strategy if strategy != "kb" else "sequential",
            )
        else:
            hypothesis = hunter.hypothesis_from_family(family)
            if strategy and strategy != "kb":
                hypothesis = hypothesis.model_copy(update={"jailbreak_strategy": strategy})

        with _lock:
            c = _campaign_store[campaign_id]
            c["hypothesis"] = hypothesis.model_dump()
        _set_agent(campaign_id, "Threat Hunter", "completed", hypothesis.name)

        # 2–4. Planner / Generator / Sandbox via runner
        _set_agent(campaign_id, "Attack Planner", "running")
        _set_agent(campaign_id, "Attack Generator", "running")
        _set_agent(campaign_id, "Sandbox Execution", "running")

        summary = run_hypothesis_campaign(
            hypothesis,
            planner,
            generator,
            client,
            analyzer,
            mutator,
            memory=memory,
            print_sections=False,
            run_id=campaign_id,
        )

        _set_agent(campaign_id, "Attack Planner", "completed")
        _set_agent(
            campaign_id,
            "Attack Generator",
            "completed",
            f"{summary.get('payloads_generated', 0)} payloads",
        )
        _set_agent(
            campaign_id,
            "Sandbox Execution",
            "completed",
            f"final={summary.get('final_decision')} gaps={summary.get('control_gaps', 0)}",
        )

        # 5. Failure Analyzer
        _set_agent(campaign_id, "Failure Analyzer", "running")
        findings_count = int(summary.get("control_gaps") or 0)
        findings = [{"type": "control_gap", "count": findings_count}]
        _set_agent(campaign_id, "Failure Analyzer", "completed", f"{findings_count} gaps")

        # 6. Memory — store strategy outcome from campaign summary
        _set_agent(campaign_id, "Memory Agent", "running")
        try:
            memory.store_strategy(
                name=hypothesis.name,
                description=f"Campaign {campaign_id} final={summary.get('final_decision')}",
                conditions={
                    "primary_family": family_id,
                    "composite_families": composites,
                    "outcome": "success" if summary.get("final_decision") == "ALLOW" else "failure",
                    "final_decision": summary.get("final_decision"),
                },
            )
        except Exception:
            pass
        mem_count = len(getattr(memory, "memories", []) or []) + len(
            getattr(memory, "strategies", []) or []
        )
        _set_agent(campaign_id, "Memory Agent", "completed", f"{mem_count} entries")

        # 7. Strategy Layer — coverage / next candidates
        _set_agent(campaign_id, "Strategy Layer", "running")
        next_action = "continue"
        try:
            report = strategy_layer.coverage_report()
            candidates = strategy_layer.prioritized_candidates(tested_ids={family_id})
            if candidates:
                next_action = f"next:{candidates[0].family_id}"
            elif report.get("coverage_pct", 0) >= 1.0:
                next_action = "complete"
        except Exception:
            next_action = "continue"
        _set_agent(campaign_id, "Strategy Layer", "completed", next_action)

        outcomes = summary.get("outcomes") or []
        blocked = sum(1 for o in outcomes if o in ("BLOCK", "blocked", "CHALLENGE", "challenged"))
        allowed = sum(1 for o in outcomes if o in ("ALLOW", "allowed", "bypass", "BYPASS"))

        with _lock:
            c = _campaign_store[campaign_id]
            c["status"] = "completed"
            c["summary"] = summary
            c["events_generated"] = summary.get("payloads_generated") or summary.get("steps_executed") or 0
            c["events_blocked"] = blocked
            c["events_allowed"] = allowed
            c["memory_entries"] = mem_count
            c["findings"] = findings
            c["strategy_state"] = {
                "current_family": family_id,
                "mutations_used": summary.get("linear_retries_used") or 0,
                "mutations_budget": c.get("mutation_budget", 2),
                "next_action": next_action,
                "reason": f"Campaign finished with final_decision={summary.get('final_decision')}",
            }
            c["finished_at"] = _now()

    except Exception as exc:
        traceback.print_exc()
        with _lock:
            c = _campaign_store.get(campaign_id)
            if c:
                c["status"] = "failed"
                c["error"] = str(exc)
                c["finished_at"] = _now()
                for step in c["timeline"]:
                    if step["status"] == "running":
                        step["status"] = "failed"
                        step["detail"] = str(exc)


@router.get("/families")
async def list_families():
    """List all KB attack families."""
    from backend.red_team.agent_helpers import OfflineKnowledge

    kb = OfflineKnowledge()
    families = []
    for fam in kb.families:
        genai = fam.get("genai") if isinstance(fam.get("genai"), dict) else {}
        families.append({
            "attack_id": fam.get("attack_id"),
            "name": fam.get("name"),
            "lifecycle_stage": fam.get("lifecycle_stage"),
            "surface": fam.get("surface", "payment"),
            "variants": fam.get("variants", []),
            "controls_targeted": fam.get("controls_targeted", []),
            "is_genai": bool(genai.get("is_genai") or genai.get("load_bearing")),
            "simulatable": fam.get("simulatable", True),
        })
    return {"families": families, "total": len(families)}


@router.post("/hypotheses")
async def generate_hypotheses(req: HypothesisRequest):
    """Run Threat Hunter to generate attack hypotheses."""
    from backend.red_team.agents.threat_hunter import ThreatHunter

    hunter = ThreatHunter()
    output = hunter.discover(
        tested_families=req.tested_families,
        prefer_composites=req.prefer_composites,
        max_hypotheses=req.max_hypotheses,
    )
    return {
        "run_id": f"hunter_{uuid.uuid4().hex[:8]}",
        "hypotheses": [h.model_dump() for h in output.hypotheses],
        "confidence": output.confidence,
    }


@router.post("/campaigns")
async def create_campaign(req: CampaignCreateRequest, background_tasks: BackgroundTasks):
    """Create a campaign and optionally execute the full Red Team pipeline."""
    campaign_id = f"camp_{uuid.uuid4().hex[:8]}"
    now = _now()
    campaign = {
        "campaign_id": campaign_id,
        "attack_family": req.attack_family,
        "composite_families": req.composite_families,
        "strategy": req.strategy,
        "campaign_size": req.campaign_size,
        "mutation_budget": req.mutation_budget,
        "status": "created",
        "safety_gate": _safety_engine.get_safety_gate_display(),
        "timeline": [
            {"agent": "Threat Hunter", "status": "waiting", "order": 1},
            {"agent": "Attack Planner", "status": "waiting", "order": 2},
            {"agent": "Attack Generator", "status": "waiting", "order": 3},
            {"agent": "Sandbox Execution", "status": "waiting", "order": 4},
            {"agent": "Failure Analyzer", "status": "waiting", "order": 5},
            {"agent": "Memory Agent", "status": "waiting", "order": 6},
            {"agent": "Strategy Layer", "status": "waiting", "order": 7},
        ],
        "events_generated": 0,
        "events_blocked": 0,
        "events_allowed": 0,
        "memory_entries": 0,
        "created_at": now,
        "updated_at": now,
        "hypothesis": None,
        "summary": None,
        "error": None,
    }
    with _lock:
        _campaign_store[campaign_id] = campaign

    if req.execute:
        background_tasks.add_task(_execute_campaign, campaign_id)
        campaign = {**campaign, "status": "queued"}

    return campaign


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    with _lock:
        if campaign_id not in _campaign_store:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return dict(_campaign_store[campaign_id])


@router.get("/campaigns/{campaign_id}/timeline")
async def get_timeline(campaign_id: str):
    with _lock:
        if campaign_id not in _campaign_store:
            raise HTTPException(status_code=404, detail="Campaign not found")
        c = _campaign_store[campaign_id]
        return {
            "campaign_id": campaign_id,
            "status": c.get("status"),
            "timeline": c["timeline"],
            "error": c.get("error"),
        }


@router.get("/campaigns/{campaign_id}/safety")
async def get_safety(campaign_id: str):
    budget = _safety_engine.get_budget()
    return {
        "campaign_id": campaign_id,
        "gate": _safety_engine.get_safety_gate_display(),
        "budget": budget.model_dump(),
    }


@router.get("/campaigns/{campaign_id}/memory")
async def get_memory(campaign_id: str):
    with _lock:
        c = _campaign_store.get(campaign_id)
        if not c:
            raise HTTPException(status_code=404, detail="Campaign not found")
        hyp = c.get("hypothesis")
        summary = c.get("summary") or {}
        memories = []
        if hyp:
            memories.append({
                "text": hyp.get("reasoning") or hyp.get("name"),
                "confidence": hyp.get("novelty_score") or 0.7,
                "type": "hypothesis",
            })
        if summary:
            memories.append({
                "text": f"Final decision={summary.get('final_decision')} gaps={summary.get('control_gaps')}",
                "confidence": 0.85,
                "type": "campaign_result",
            })
        return {
            "campaign_id": campaign_id,
            "memories": memories,
            "total_entries": c.get("memory_entries") or len(memories),
        }


@router.get("/campaigns/{campaign_id}/strategy")
async def get_strategy(campaign_id: str):
    with _lock:
        if campaign_id not in _campaign_store:
            raise HTTPException(status_code=404, detail="Campaign not found")
        c = _campaign_store[campaign_id]
        state = c.get("strategy_state") or {
            "current_family": c["attack_family"],
            "mutations_used": 0,
            "mutations_budget": c["mutation_budget"],
            "next_action": "awaiting_execution" if c["status"] in ("created", "queued") else c["status"],
            "reason": c.get("error") or f"Campaign status={c['status']}",
        }
        return {"campaign_id": campaign_id, **state}


@router.post("/campaigns/{campaign_id}/stop")
async def stop_campaign(campaign_id: str):
    with _lock:
        if campaign_id not in _campaign_store:
            raise HTTPException(status_code=404, detail="Campaign not found")
        c = _campaign_store[campaign_id]
        if c["status"] in ("completed", "failed", "stopped"):
            return {"status": c["status"], "campaign_id": campaign_id}
        c["status"] = "stopped"
        c["finished_at"] = _now()
        for step in c["timeline"]:
            if step["status"] in ("waiting", "running"):
                step["status"] = "stopped"
        return {"status": "stopped", "campaign_id": campaign_id}
