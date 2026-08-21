"""
Knowledge Base API Service
Exposes attack families, signals, and lifecycle stages via REST endpoints.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from urllib.parse import unquote

from src.backend.knowledge.loader import KnowledgeLoader

app = FastAPI(
    title="Payment Defense Twin - Knowledge Base API",
    description="Serves attack families, signals, and lifecycle stages for Red Team, Sandbox, and Blue Team",
    version="1.0.0"
)

# Initialize loader once
loader = KnowledgeLoader()

# ============================================================
# Response Models
# ============================================================

class AttackFamilyResponse(BaseModel):
    attack_id: str
    name: str
    variants: List[str]
    lifecycle_stage: str
    genai_classification: str
    simulation_type: str
    prerequisites: List[str]
    attack_flow: List[str]
    detection_signals: List[Dict]
    controls_targeted: List[str]
    evidence_confidence: str

class SignalResponse(BaseModel):
    signal_name: str
    category: str
    description: str
    detection_method: str
    false_positive_risk: str
    cross_account_needed: bool

class LifecycleStageResponse(BaseModel):
    stage: str
    controls: List[str]

# ============================================================
# Endpoints
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "Payment Defense Twin - Knowledge Base API",
        "endpoints": [
            "/families",
            "/families/{family_id}",
            "/families/stage/{stage}",
            "/families/stage/slug/{slug}",
            "/signals",
            "/signals/family/{family_id}",
            "/stages",
            "/stages/controls",
            "/stats",
            "/debug/available-stages"
        ]
    }

@app.get("/stats")
async def get_stats():
    """Get overview statistics of the knowledge base."""
    return {
        "total_families": len(loader.families),
        "total_signals": len(loader.signals),
        "total_stages": len(loader.stages),
        "families_by_stage": {
            stage: len(loader.get_families_by_stage(stage))
            for stage in loader.get_all_controls().keys()
        }
    }

@app.get("/families", response_model=List[AttackFamilyResponse])
async def get_all_families(
    stage: Optional[str] = None,
    genai_class: Optional[str] = None,
    limit: int = 100
):
    """Get all attack families, optionally filtered by stage or GenAI classification."""
    families = loader.families
    
    if stage:
        families = [f for f in families if f.get("lifecycle_stage") == stage]
    
    if genai_class:
        families = [f for f in families if f.get("genai_classification") == genai_class]
    
    return families[:limit]

@app.get("/families/{family_id}", response_model=AttackFamilyResponse)
async def get_family(family_id: str):
    """Get a specific attack family by ID."""
    family = loader.get_family(family_id)
    if not family:
        raise HTTPException(status_code=404, detail=f"Family {family_id} not found")
    return family

@app.get("/families/stage/{stage}")
async def get_families_by_stage(stage: str):
    """Get all families that target a specific lifecycle stage.
    
    Supports URL-encoded characters like %20 (space) and %2F (/).
    Falls back to case‑insensitive and partial matching.
    """
    # Decode URL-encoded characters
    decoded_stage = unquote(stage)
    
    # Try exact match first
    families = loader.get_families_by_stage(decoded_stage)
    
    # If no exact match, try case-insensitive
    if not families:
        stage_lower = decoded_stage.lower()
        families = [
            f for f in loader.families 
            if f.get("lifecycle_stage", "").lower() == stage_lower
        ]
    
    # If still no matches, try partial match (contains)
    if not families:
        families = [
            f for f in loader.families 
            if decoded_stage.lower() in f.get("lifecycle_stage", "").lower()
        ]
    
    if not families:
        # Get all available stages for helpful error message
        available_stages = sorted(set(
            f.get("lifecycle_stage") for f in loader.families 
            if f.get("lifecycle_stage")
        ))
        raise HTTPException(
            status_code=404, 
            detail=f"No families found for stage '{decoded_stage}'. Available stages: {available_stages}"
        )
    
    return families

@app.get("/families/stage/slug/{slug}")
async def get_families_by_stage_slug(slug: str):
    """Get families by a simplified stage slug.
    
    This provides cleaner URLs for common stage names.
    Examples:
    - /families/stage/slug/aml-compliance
    - /families/stage/slug/authentication
    - /families/stage/slug/payment-rail
    """
    # Comprehensive slug map (based on debug output)
    stage_map = {
        "ai-agent-commerce": "AI-Agent Commerce",
        "ai-agent-commerce-cross-stage": "AI-Agent Commerce / Cross-stage",
        "aml-compliance": "AML / Compliance",
        "acquirer": "Acquirer (Stage 7 — Onboarding/Underwriting)",
        "acquirer-monitoring": "Acquirer (Stage 7 — Ongoing Monitoring)",
        "acquirer-portfolio": "Acquirer (Stage 7 — Portfolio Monitoring)",
        "acquirer-mcc": "Acquirer (Stage 7 — MCC Assignment / Content Monitoring)",
        "authentication": "Authentication",
        "authorization": "Authorization (Stage 10)",
        "cashout-mule-recruitment": "Cash-out/Mule (Recruitment)",
        "cashout-mule-conversion": "Cash-out/Mule (Conversion/Cash-Out)",
        "cross-stage-kyc-mule": "Cross-stage (KYC/Account Creation/Mule)",
        "cross-stage-network": "Cross-stage/Network",
        "device-session": "Device / Session (Stage 3)",
        "gateway-processor": "Gateway / Processor",
        "identity-kyc": "Identity / KYC (Stage 1)",
        "identity-kyc-post-verification": "Identity / KYC (Stage 1) — post-verification exploitation",
        "identity-kyc-recovery": "Identity / KYC (Stage 1) — recovery verification",
        "account-creation": "Account Creation / Onboarding (Stage 2)",
        "account-creation-activation": "Account Creation / Onboarding (Stage 2 — Activation / Recovery)",
        "payment-rail": "Payment Rail",
        "open-banking-consent": "Third-Party / Open Banking (Consent Granting)",
        "open-banking-tpp-onboarding": "Third-Party / Open Banking (TPP Onboarding / Customer Acquisition)",
        "open-banking-tpp-operations": "Third-Party / Open Banking (TPP Operations / API Usage)",
        "open-banking-token": "Third-Party / Open Banking (API Authorisation / Token Usage)",
        "open-banking-scope": "Third-Party / Open Banking (Consent Scope Enforcement)",
        "open-banking-aisp": "Third-Party / Open Banking (AISP Data Access)",
    }
    
    stage_name = stage_map.get(slug.lower())
    if not stage_name:
        available_slugs = sorted(stage_map.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Unknown stage slug '{slug}'. Available slugs: {available_slugs}"
        )
    
    families = loader.get_families_by_stage(stage_name)
    if not families:
        # Try partial match as fallback (some stages may have slight variations)
        families = [
            f for f in loader.families 
            if stage_name.lower() in f.get("lifecycle_stage", "").lower()
        ]
    
    if not families:
        raise HTTPException(
            status_code=404,
            detail=f"No families found for stage '{stage_name}'"
        )
    
    return families

@app.get("/signals", response_model=List[SignalResponse])
async def get_all_signals(
    category: Optional[str] = None,
    limit: int = 200
):
    """Get all detection signals, optionally filtered by category."""
    signals = loader.signals
    if category:
        signals = [s for s in signals if s.get("category") == category]
    return signals[:limit]

@app.get("/signals/family/{family_id}")
async def get_signals_for_family(family_id: str):
    """Get detection signals specific to an attack family."""
    signals = loader.get_signals_by_family(family_id)
    if not signals:
        return []
    return signals

@app.get("/stages", response_model=List[LifecycleStageResponse])
async def get_all_stages():
    """Get all lifecycle stages."""
    return loader.stages

@app.get("/stages/controls")
async def get_all_controls():
    """Get the control mapping for all lifecycle stages."""
    return loader.get_all_controls()

@app.get("/stages/{stage}/controls")
async def get_controls_for_stage(stage: str):
    """Get controls for a specific lifecycle stage."""
    decoded_stage = unquote(stage)
    controls = loader.get_all_controls()
    
    # Try exact match first
    if decoded_stage in controls:
        return {"stage": decoded_stage, "controls": controls[decoded_stage]}
    
    # Try case-insensitive match
    for key in controls.keys():
        if key.lower() == decoded_stage.lower():
            return {"stage": key, "controls": controls[key]}
    
    # Try partial match
    for key in controls.keys():
        if decoded_stage.lower() in key.lower():
            return {"stage": key, "controls": controls[key]}
    
    raise HTTPException(
        status_code=404, 
        detail=f"Stage '{decoded_stage}' not found. Available stages: {sorted(controls.keys())}"
    )

# ============================================================
# Debug Endpoints
# ============================================================

@app.get("/debug/available-stages")
async def get_available_stages():
    """Debug: See all available lifecycle stages in the data."""
    stages = {}
    for family in loader.families:
        stage = family.get("lifecycle_stage")
        if stage:
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(family.get("attack_id"))
    
    return {
        "available_stages": sorted(stages.keys()),
        "count_by_stage": {k: len(v) for k, v in stages.items()},
        "families_by_stage": stages,
        "stage_slug_map": {
            "ai-agent-commerce": "AI-Agent Commerce",
            "ai-agent-commerce-cross-stage": "AI-Agent Commerce / Cross-stage",
            "aml-compliance": "AML / Compliance",
            "acquirer": "Acquirer (Stage 7 — Onboarding/Underwriting)",
            "acquirer-monitoring": "Acquirer (Stage 7 — Ongoing Monitoring)",
            "acquirer-portfolio": "Acquirer (Stage 7 — Portfolio Monitoring)",
            "acquirer-mcc": "Acquirer (Stage 7 — MCC Assignment / Content Monitoring)",
            "authentication": "Authentication",
            "authorization": "Authorization (Stage 10)",
            "cashout-mule-recruitment": "Cash-out/Mule (Recruitment)",
            "cashout-mule-conversion": "Cash-out/Mule (Conversion/Cash-Out)",
            "cross-stage-kyc-mule": "Cross-stage (KYC/Account Creation/Mule)",
            "cross-stage-network": "Cross-stage/Network",
            "device-session": "Device / Session (Stage 3)",
            "gateway-processor": "Gateway / Processor",
            "identity-kyc": "Identity / KYC (Stage 1)",
            "identity-kyc-post-verification": "Identity / KYC (Stage 1) — post-verification exploitation",
            "identity-kyc-recovery": "Identity / KYC (Stage 1) — recovery verification",
            "account-creation": "Account Creation / Onboarding (Stage 2)",
            "account-creation-activation": "Account Creation / Onboarding (Stage 2 — Activation / Recovery)",
            "payment-rail": "Payment Rail",
            "open-banking-consent": "Third-Party / Open Banking (Consent Granting)",
            "open-banking-tpp-onboarding": "Third-Party / Open Banking (TPP Onboarding / Customer Acquisition)",
            "open-banking-tpp-operations": "Third-Party / Open Banking (TPP Operations / API Usage)",
            "open-banking-token": "Third-Party / Open Banking (API Authorisation / Token Usage)",
            "open-banking-scope": "Third-Party / Open Banking (Consent Scope Enforcement)",
            "open-banking-aisp": "Third-Party / Open Banking (AISP Data Access)",
        }
    }

@app.get("/debug/families-sample")
async def get_families_sample(limit: int = 5):
    """Debug: See a sample of loaded families."""
    return {
        "total": len(loader.families),
        "sample": loader.families[:limit]
    }

@app.get("/debug/signals-sample")
async def get_signals_sample(limit: int = 5):
    """Debug: See a sample of loaded signals."""
    return {
        "total": len(loader.signals),
        "sample": loader.signals[:limit]
    }

# ============================================================
# Startup Event
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Log loaded data statistics on startup."""
    print(f"✅ Knowledge Base API started successfully!")
    print(f"📊 Loaded {len(loader.families)} attack families")
    print(f"📊 Loaded {len(loader.signals)} detection signals")
    print(f"📊 Loaded {len(loader.stages)} lifecycle stages")
    
    if loader.families:
        available_stages = sorted(set(
            f.get("lifecycle_stage") for f in loader.families 
            if f.get("lifecycle_stage")
        ))
        print(f"📊 Available stages: {available_stages}")

# ============================================================
# Run with: uvicorn src.backend.api.knowledge_api:app --reload
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
