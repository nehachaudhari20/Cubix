"""Governance API — safety policy, model registry, experiment provenance, data metadata."""

from __future__ import annotations

from fastapi import APIRouter

from backend.governance.config import get_risk_policy
from backend.safety.policy_engine import SimulationPolicyEngine

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

_safety = SimulationPolicyEngine()


@router.get("/safety")
async def get_safety_policy():
    """Return safety policy and restrictions."""
    return {
        "policy": {
            "max_amount": 100000,
            "max_mutations_per_family": 2,
            "max_campaign_iterations": 5,
            "max_events_per_campaign": 250,
            "max_composite_families": 3,
            "prohibited_actions": [
                "live_payment_initiation",
                "real_identity_generation",
                "credential_generation",
                "otp_capture",
                "external_endpoint_scanning",
            ],
            "data_scope": "SYNTHETIC_ONLY",
            "live_rail_access": "Disabled",
            "external_network_access": "Disabled",
        },
        "gate_checks": _safety.get_safety_gate_display(),
    }


@router.get("/model-registry")
async def get_model_registry():
    """Return all model versions and artifacts."""
    from pathlib import Path
    import json

    model_dir = Path("data/models")
    registry = []

    # v1
    v1_spec = model_dir / "features_v1_backup.json"
    if v1_spec.exists():
        with open(v1_spec) as f:
            spec = json.load(f)
        registry.append({
            "version": "v1",
            "model_type": spec.get("model_type", "XGBoost"),
            "status": "archived",
            "artifacts": [str(p) for p in model_dir.glob("fraudshield_v1*")],
            "feature_count": len(spec.get("feature_order", [])),
        })

    # v3
    v3_spec = model_dir / "features.json"
    if v3_spec.exists():
        with open(v3_spec) as f:
            spec = json.load(f)
        v3_dir = model_dir / "fraudshield_v3"
        registry.append({
            "version": "v3",
            "model_type": spec.get("model_type", "unknown"),
            "status": "deployed",
            "artifacts": [str(p) for p in v3_dir.glob("*")] if v3_dir.exists() else [],
            "feature_count": len(spec.get("feature_order", [])),
        })

    return {"registry": registry, "active_version": "v3"}


@router.get("/experiment/{experiment_id}")
async def get_experiment_provenance(experiment_id: str):
    """Return reproducibility manifest for an experiment."""
    policy = get_risk_policy()
    return {
        "experiment_id": experiment_id,
        "data_scope": "SYNTHETIC_ONLY",
        "policy_version": policy.version,
        "active_model": "fraudshield_v3",
        "reproduction_steps": [
            "Load KB families from data/kb/families/",
            "Run Red Team agents to generate campaigns",
            "Execute campaigns in Payment Sandbox (synthetic only)",
            "Score events with FraudShield v3 ensemble",
            "Analyze failures with FailureAnalyzer",
            "Store lessons in Memory Agent",
        ],
        "artifacts": {
            "kb": "data/kb/families/",
            "models": "data/models/",
            "buffer": "data/adversarial_buffer/",
            "evaluation": "data/evaluation/",
        },
    }


@router.get("/data/metadata")
async def get_data_metadata():
    """Dataset limitations and synthetic field documentation."""
    return {
        "data_scope": "SYNTHETIC_ONLY",
        "synthetic_fields": [
            "All customer IDs are generated UUIDs",
            "All PANs are synthetic test numbers",
            "All device fingerprints are generated",
            "All transaction amounts are simulated",
            "All merchant IDs are synthetic",
        ],
        "limitations": [
            "This is a prototype validation environment",
            "Not intended for production fraud detection",
            "All metrics are on synthetic data only",
            "Real-world performance may differ",
        ],
        "non_real_data": [
            "No real payment card data",
            "No real customer PII",
            "No real transaction records",
            "No real merchant data",
            "No real device identifiers",
        ],
    }
