"""Blue Team v1 API — scoring, ensemble breakdown, explainability, policy, audit."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.governance.config import RiskPolicy, get_risk_policy
from backend.safety.policy_engine import SimulationPolicyEngine

router = APIRouter(prefix="/api/v1/blue-team", tags=["blue-team-v1"])

# In-memory score store (production would use DB)
_score_store: Dict[str, Dict[str, Any]] = {}


# ── Schemas ───────────────────────────────────────────────────────

class ScoreRequest(BaseModel):
    event_id: str
    campaign_id: Optional[str] = None
    model_version: str = "fraudshield_v3"
    policy_version: str = "risk_policy_v1_2"
    include_explanation: bool = True
    include_ensemble_breakdown: bool = True


class ScoreBatchRequest(BaseModel):
    events: List[Dict[str, Any]]
    campaign_id: Optional[str] = None
    model_version: str = "fraudshield_v3"


class RetrainRequest(BaseModel):
    trigger: str = "manual"
    families: List[str] = Field(default_factory=list)
    force: bool = False


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/models")
async def list_models():
    """Return FraudShield model versions and metadata."""
    from backend.blue_team.fraudshield import load_fraudshield
    from pathlib import Path
    import json

    model_dir = Path("data/models")
    models = []

    # Check v1
    v1_spec = model_dir / "features_v1_backup.json"
    if v1_spec.exists():
        with open(v1_spec) as f:
            spec = json.load(f)
        models.append({
            "version": "v1",
            "type": spec.get("model_type", "XGBoost"),
            "status": "archived",
            "role": "Baseline booster — trained on historical fraud data",
            "training_data": "Historical baseline + known fraud",
        })

    # Check v3 (active)
    v3_spec = model_dir / "features.json"
    if v3_spec.exists():
        with open(v3_spec) as f:
            spec = json.load(f)
        mt = spec.get("model_type", "unknown")
        models.append({
            "version": "v3",
            "type": mt,
            "status": "deployed" if mt == "StackedEnsemble" else "active",
            "role": "Stacked Ensemble — XGBoost + LightGBM + Logistic → Meta Learner" if mt == "StackedEnsemble" else "Single booster",
            "training_data": "v2 + adversarial examples from Red Team",
            "components": {
                "xgboost": "Non-linear transaction/behavior patterns",
                "lightgbm": "Complementary gradient-boosted signals",
                "logistic": "Stable linear decision boundary",
                "meta_learner": "Combines base model probabilities",
                "isolation_forest": "Novel distribution anomaly detection",
            } if mt == "StackedEnsemble" else None,
        })

    # Check anomaly model
    anomaly_path = model_dir / "fraudshield_v3" / "isolation_forest.pkl"
    if anomaly_path.exists():
        models.append({
            "version": "v3-anomaly",
            "type": "IsolationForest",
            "status": "active",
            "role": "Unsupervised anomaly detection — trained on legitimate baseline only",
        })

    return {"models": models, "active_version": "v3"}


@router.get("/models/{version}")
async def get_model_detail(version: str):
    """Return detailed metrics for a specific model version."""
    from pathlib import Path
    import json

    model_dir = Path("data/models")

    # Try loading hardening report
    report_path = model_dir / "hardening_report.json"
    if report_path.exists():
        with open(report_path) as f:
            report = json.load(f)
        detection = report.get("detection", {})
        return {
            "version": version,
            "metrics": {
                "pr_auc": detection.get("pr_auc"),
                "roc_auc": detection.get("roc_auc"),
                "f1": detection.get("f1"),
                "precision": detection.get("precision"),
                "recall": detection.get("recall"),
                "fpr": detection.get("fpr"),
            },
            "training_manifest": report.get("training_manifest", {}),
            "feature_count": len(report.get("feature_order", [])),
        }

    return {"version": version, "metrics": {}, "note": "No training report available"}


@router.post("/score")
async def score_event(req: ScoreRequest):
    """Score a single event through FraudShield and return detailed breakdown."""
    policy = get_risk_policy()

    # Simulate ensemble scores (in production, run actual model)
    import random
    random.seed(hash(req.event_id))

    xgb_prob = round(random.uniform(0.1, 0.95), 4)
    lgb_prob = round(random.uniform(0.1, 0.95), 4)
    log_prob = round(random.uniform(0.1, 0.95), 4)
    meta_prob = round(0.4 * xgb_prob + 0.3 * lgb_prob + 0.3 * log_prob, 4)
    anomaly = round(random.uniform(0.1, 0.9), 4)
    rule_risk = round(random.uniform(0.1, 0.95), 4)

    blend = policy.blend.normalized()
    final = round(
        blend.rule_risk * rule_risk +
        blend.ml_score * meta_prob +
        blend.anomaly_score * anomaly,
        4
    )

    decision = policy.decide(final)

    # Generate reason codes
    reason_codes = []
    if rule_risk > 0.7:
        reason_codes.append({"code": "VELOCITY_1H_HIGH", "severity": "HIGH", "label": "High transaction velocity"})
    if anomaly > 0.6:
        reason_codes.append({"code": "DEVICE_NOVELTY", "severity": "MEDIUM", "label": "New or rare device profile"})
    if meta_prob > 0.7:
        reason_codes.append({"code": "SYNTHETIC_IDENTITY_PATTERN", "severity": "HIGH", "label": "Identity pattern requires review"})
    if final > 0.8:
        reason_codes.append({"code": "HIGH_RISK_COMPOSITE", "severity": "CRITICAL", "label": "Multiple high-risk signals compound"})

    score_id = f"score_{uuid.uuid4().hex[:6]}"
    result = {
        "score_id": score_id,
        "event_id": req.event_id,
        "model": {
            "name": "FraudShield",
            "version": req.model_version,
            "type": "StackedEnsemble",
        },
        "scores": {
            "xgboost_probability": xgb_prob,
            "lightgbm_probability": lgb_prob,
            "logistic_probability": log_prob,
            "meta_learner_probability": meta_prob,
            "anomaly_score": anomaly,
            "rule_risk": rule_risk,
            "final_blended_risk": final,
        },
        "decision": {
            "action": decision,
            "threshold": policy.thresholds.block_min,
            "policy_override": False,
        },
        "latency_ms": round(random.uniform(15, 45), 1),
        "reason_codes": reason_codes,
        "blend_weights": blend.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _score_store[score_id] = result
    return result


@router.post("/score/batch")
async def score_batch(req: ScoreBatchRequest):
    """Batch score campaign events."""
    results = []
    for event in req.events:
        event_id = event.get("event_id", event.get("transaction_id", f"evt_{uuid.uuid4().hex[:6]}"))
        single = await score_event(ScoreRequest(
            event_id=event_id,
            campaign_id=req.campaign_id,
            model_version=req.model_version,
        ))
        results.append(single)

    allowed = sum(1 for r in results if r["decision"]["action"] == "ALLOW")
    challenged = sum(1 for r in results if r["decision"]["action"] == "CHALLENGE")
    blocked = sum(1 for r in results if r["decision"]["action"] == "BLOCK")
    total = len(results)

    return {
        "total": total,
        "allowed": allowed,
        "challenged": challenged,
        "blocked": blocked,
        "strict_asr": round(allowed / max(1, total), 3),
        "results": results,
    }


@router.get("/score/{score_id}/ensemble")
async def get_ensemble(score_id: str):
    """Return base model contributions for a scored event."""
    if score_id not in _score_store:
        raise HTTPException(status_code=404, detail="Score not found")
    s = _score_store[score_id]
    return {
        "score_id": score_id,
        "ensemble": {
            "xgboost": s["scores"]["xgboost_probability"],
            "lightgbm": s["scores"]["lightgbm_probability"],
            "logistic": s["scores"]["logistic_probability"],
            "meta_learner": s["scores"]["meta_learner_probability"],
            "isolation_forest": s["scores"]["anomaly_score"],
            "rule_risk": s["scores"]["rule_risk"],
        },
        "final": s["scores"]["final_blended_risk"],
    }


@router.get("/score/{score_id}/explain")
async def get_explanation(score_id: str):
    """Return SHAP-style explanation and reason codes."""
    if score_id not in _score_store:
        raise HTTPException(status_code=404, detail="Score not found")
    s = _score_store[score_id]
    return {
        "score_id": score_id,
        "reason_codes": s["reason_codes"],
        "feature_impact": [
            {"feature": "velocity_1h", "impact": 0.23, "direction": "increases_risk"},
            {"feature": "new_device", "impact": 0.18, "direction": "increases_risk"},
            {"feature": "amount_growth_ratio", "impact": 0.15, "direction": "increases_risk"},
            {"feature": "graph_flag", "impact": 0.12, "direction": "increases_risk"},
            {"feature": "behavioral_flag", "impact": 0.09, "direction": "increases_risk"},
            {"feature": "device_age_days", "impact": -0.07, "direction": "decreases_risk"},
            {"feature": "merchant_risk", "impact": 0.06, "direction": "increases_risk"},
        ],
    }


@router.get("/score/{score_id}/policy")
async def get_policy(score_id: str):
    """Return blend contribution and action policy for a scored event."""
    if score_id not in _score_store:
        raise HTTPException(status_code=404, detail="Score not found")
    s = _score_store[score_id]
    policy = get_risk_policy()
    return {
        "score_id": score_id,
        "blend_weights": policy.blend.model_dump(),
        "thresholds": policy.thresholds.model_dump(),
        "scores": s["scores"],
        "decision": s["decision"],
    }


@router.get("/score/{score_id}/audit")
async def get_audit(score_id: str):
    """Return full auditable scoring record."""
    if score_id not in _score_store:
        raise HTTPException(status_code=404, detail="Score not found")
    s = _score_store[score_id]
    return {
        "audit_record": s,
        "data_scope": "SYNTHETIC_ONLY",
        "note": "All scoring performed on synthetic sandbox events only",
    }


@router.post("/retrain")
async def request_retrain(req: RetrainRequest):
    """Request a controlled retrain."""
    job_id = f"retrain_{uuid.uuid4().hex[:6]}"
    return {
        "job_id": job_id,
        "status": "queued",
        "trigger": req.trigger,
        "families": req.families,
        "message": "Retrain request queued. In production, this would trigger a controlled retraining pipeline.",
    }
