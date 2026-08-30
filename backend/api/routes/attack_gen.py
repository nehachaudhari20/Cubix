"""
Attack Generation API — bulk 1500-transaction generation + RAG-powered attack query.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/attack-gen", tags=["attack-generation"])

# In-memory store for generated batches
_batches: Dict[str, Dict[str, Any]] = {}


class GenerateRequest(BaseModel):
    count: int = Field(default=1500, ge=1, le=10000)
    focus_family: Optional[str] = None
    focus_stage: Optional[str] = None
    seed: int = 42


class RAGQueryRequest(BaseModel):
    query: str
    focus_family: Optional[str] = None
    max_results: int = 10


@router.post("/generate")
async def generate_transactions(req: GenerateRequest):
    """Generate synthetic attack transactions covering all 57 KB families."""
    from backend.attack_generator.transaction_factory import TransactionFactory

    start = time.time()
    factory = TransactionFactory(seed=req.seed)
    txns = factory.generate_batch(
        target_count=req.count,
        focus_family=req.focus_family,
        focus_stage=req.focus_stage,
    )
    summary = factory.get_summary(txns)
    elapsed = round(time.time() - start, 3)

    batch_id = f"batch_{req.seed}_{req.count}"
    _batches[batch_id] = {
        "id": batch_id,
        "transactions": [tx.to_dict() for tx in txns],
        "summary": summary,
        "elapsed_seconds": elapsed,
    }

    return {
        "batch_id": batch_id,
        "count": len(txns),
        "summary": summary,
        "elapsed_seconds": elapsed,
        "transactions": [tx.to_dict() for tx in txns[:50]],  # Return first 50 for preview
        "total_available": len(txns),
    }


@router.get("/batch/{batch_id}")
async def get_batch(batch_id: str, offset: int = 0, limit: int = 100):
    """Retrieve transactions from a generated batch with pagination."""
    if batch_id not in _batches:
        return {"error": "Batch not found"}
    batch = _batches[batch_id]
    txns = batch["transactions"][offset:offset + limit]
    return {
        "batch_id": batch_id,
        "offset": offset,
        "limit": limit,
        "total": len(batch["transactions"]),
        "transactions": txns,
    }


@router.get("/summary/{batch_id}")
async def get_batch_summary(batch_id: str):
    """Get summary statistics for a batch."""
    if batch_id not in _batches:
        return {"error": "Batch not found"}
    return _batches[batch_id]["summary"]


@router.get("/families/{batch_id}")
async def get_family_breakdown(batch_id: str):
    """Get per-family breakdown for a batch."""
    if batch_id not in _batches:
        return {"error": "Batch not found"}
    batch = _batches[batch_id]
    families = {}
    for tx in batch["transactions"]:
        fam = tx["attack_family"]
        if fam not in families:
            families[fam] = {
                "family": fam,
                "name": tx["family_name"],
                "stage": tx["lifecycle_stage"],
                "total": 0,
                "blocked": 0,
                "challenged": 0,
                "allowed": 0,
                "avg_risk": 0,
                "total_risk": 0,
            }
        families[fam]["total"] += 1
        families[fam][tx["decision"].lower() + "d"] = families[fam].get(tx["decision"].lower() + "d", 0) + 1
        families[fam]["total_risk"] += tx["risk_score"]

    for fam in families.values():
        fam["avg_risk"] = round(fam["total_risk"] / fam["total"], 4)
        fam["asr"] = round(fam["allowed"] / fam["total"] * 100, 1) if fam["total"] > 0 else 0
        del fam["total_risk"]

    return {"families": list(families.values()), "total_families": len(families)}


@router.post("/rag/query")
async def rag_query(req: RAGQueryRequest):
    """Query the RAG system for relevant attack knowledge."""
    from backend.rag.rag_service import retrieve_for_attack, format_rag_context

    start = time.time()
    ctx = retrieve_for_attack(req.query, focus_family=req.focus_family)
    context_text = format_rag_context(ctx)
    elapsed = round(time.time() - start, 3)

    return {
        "query": req.query,
        "families_found": len(ctx.get("families", [])),
        "vectors_found": len(ctx.get("vectors", [])),
        "signals_found": len(ctx.get("signals", [])),
        "stages_found": len(ctx.get("stages", [])),
        "context": context_text,
        "families": ctx.get("families", []),
        "vectors": ctx.get("vectors", []),
        "elapsed_seconds": elapsed,
    }


@router.post("/rag/attack")
async def rag_powered_attack(req: RAGQueryRequest):
    """Generate attack ideas using RAG-retrieved KB context + LLM."""
    from backend.rag.rag_service import retrieve_for_attack, format_rag_context
    from backend.llm.provider import get_llm, invoke_text

    # Retrieve relevant KB context
    ctx = retrieve_for_attack(req.query, focus_family=req.focus_family)
    context_text = format_rag_context(ctx)

    # Get LLM
    llm = get_llm()
    if not llm:
        return {"error": "LLM not configured", "hint": "Set COHERE_API_KEY and RED_TEAM_USE_LLM=true in .env"}

    system_prompt = """You are Dr. Shadow, a payment fraud Red Team researcher.
Using the KB context provided, design a detailed attack scenario.
Provide JSON with: name, attack_flow (array of steps), controls_targeted, evasion_technique, detection_signals, blue_team_recommendation.
Return ONLY a JSON object."""

    user_prompt = f"""KB Context:
{context_text}

Design an attack for: {req.query}

Focus family: {req.focus_family or 'any'}
Return a JSON object with the attack design."""

    start = time.time()
    response = invoke_text(llm, system_prompt, user_prompt)
    elapsed = round(time.time() - start, 3)

    if not response:
        return {"error": "No LLM response"}

    # Try to parse JSON
    import json
    attack = None
    try:
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            attack = json.loads(response[json_start:json_end])
    except json.JSONDecodeError:
        attack = {"raw_response": response}

    return {
        "query": req.query,
        "kb_context_families": len(ctx.get("families", [])),
        "attack": attack,
        "elapsed_seconds": elapsed,
    }


@router.get("/batches")
async def list_batches():
    """List all generated batches."""
    return {
        "batches": [
            {"id": b["id"], "count": len(b["transactions"]), "summary": b["summary"]}
            for b in _batches.values()
        ]
    }
