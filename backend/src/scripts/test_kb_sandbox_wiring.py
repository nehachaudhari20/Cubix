#!/usr/bin/env python3
"""KB wiring + flexible sandbox orchestration tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.red_team.agent_helpers import OfflineKnowledge
from backend.red_team.kb_campaign_builder import is_simulatable, build_plan_from_family
from backend.sandbox.lifecycle_router import derive_entry_point, resolve_payment_path, PAYMENT_PATHS
from backend.sandbox import PaymentSandbox, ActionType


def test_all_families_simulatable():
    kb = OfflineKnowledge()
    total = len(kb.families)
    sim = [f for f in kb.families if is_simulatable(f)]
    assert len(sim) == total, f"Expected all {total} families simulatable, got {len(sim)}"
    print(f"simulatable: {len(sim)}/{total}")


def test_entry_points():
    kb = OfflineKnowledge()
    sep = kb.get_family("SEP-001")
    ag = kb.get_family("AG-001")
    acq = kb.get_family("ACQ-001")
    assert derive_entry_point(sep) == "social_engineering"
    assert derive_entry_point(ag) == "genai_proxy"
    assert derive_entry_point(acq) == "merchant"
    print("entry points: SEP=social AG=genai ACQ=merchant")


def test_sep_plan_has_genai_and_payment():
    kb = OfflineKnowledge()
    family = kb.get_family("SEP-001")
    plan = build_plan_from_family(family, kb.stages, kb.signals)
    actions = [s.action_type for s in plan.steps]
    assert "simulate_genai_context" in actions
    assert "initiate_payment" in actions
    assert plan.entry_point == "social_engineering"
    print(f"SEP-001 plan: {actions}")


def test_ag_plan_cross_stage():
    kb = OfflineKnowledge()
    family = kb.get_family("AG-001")
    plan = build_plan_from_family(family, kb.stages, kb.signals)
    actions = [s.action_type for s in plan.steps]
    assert "simulate_genai_context" in actions
    print(f"AG-001 plan: {actions} entry={plan.entry_point}")


def test_payment_paths():
    assert resolve_payment_path({"payment_path": "risk_only"}) == "risk_only"
    assert "kyc" not in PAYMENT_PATHS["risk_only"]
    assert "kyc" in PAYMENT_PATHS["full"]
    print("payment paths OK")


def test_genai_context_sandbox():
    sandbox = PaymentSandbox()
    sandbox.execute(ActionType.REGISTER_CUSTOMER.value, {
        "customer_id": "C_victim",
        "name": "Victim",
        "pan": "PAN123",
        "dob": "1985-01-01",
        "address": "City",
        "trust_score": 0.85,
        "verified": True,
        "account_age_days": 900,
    })
    obs = sandbox.execute(ActionType.SIMULATE_GENAI_CONTEXT.value, {
        "attack_family": "SEP-001",
        "customer_id": "C_victim",
        "channels": ["voice", "email"],
        "victim_coerced": True,
        "genai_features": {"social_engineering_score": 0.85},
    })
    assert obs.decision in ("PASS", "CHALLENGE", "BLOCK")
    assert obs.state_snapshot.get("genai_features")
    print(f"genai context: decision={obs.decision} triggers={obs.control_triggers[:3]}")


def test_risk_only_payment():
    sandbox = PaymentSandbox()
    sandbox.execute(ActionType.REGISTER_CUSTOMER.value, {
        "customer_id": "C1",
        "name": "User",
        "pan": "PAN1",
        "dob": "1990-01-01",
        "address": "X",
        "trust_score": 0.9,
        "verified": True,
        "account_age_days": 400,
    })
    sandbox.execute(ActionType.REGISTER_DEVICE.value, {
        "device_id": "D1",
        "customer_id": "C1",
    })
    obs = sandbox.execute(ActionType.INITIATE_PAYMENT.value, {
        "transaction_id": "T1",
        "customer_id": "C1",
        "device_id": "D1",
        "amount": 45000,
        "payment_path": "risk_only",
        "genai_features": {"victim_coerced": 1.0, "social_engineering_score": 0.8},
        "attack_family": "SEP-001",
        "victim_coerced": True,
    })
    steps = [j.step for j in obs.journey]
    assert "KYC" not in steps
    assert "Risk" in steps
    print(f"risk_only payment journey: {steps} decision={obs.decision}")


def test_genai_kb_engine_ag001():
    from backend.sandbox.engines.genai_engine import GenAIEngine, GENAI_FEATURE_NAMES
    engine = GenAIEngine()
    result = engine.evaluate(
        attack_family_id="AG-001",
        variant_id="VAR-AG-001-02",
        payload={"channels": ["web"]},
    )
    assert result.risk_contribution > 0.5
    assert result.evidence.get("load_bearing") is True
    assert len(result.genai_features) >= len(GENAI_FEATURE_NAMES) - 2
    assert result.evidence.get("capability_ids")
    assert "prompt_injection_risk" in result.genai_features
    print(f"AG-001 KB engine: risk={result.risk_contribution} features_active={result.evidence.get('active_features')}")


def test_lifecycle_registry_covers_stages():
    from backend.sandbox.lifecycle_engine_registry import STAGE_TO_ENGINE, ENGINE_CATALOG
    assert len(STAGE_TO_ENGINE) == 49
    assert len(ENGINE_CATALOG) >= 15
    print(f"lifecycle: {len(STAGE_TO_ENGINE)} stages -> {len(ENGINE_CATALOG)} engines")


def test_expanded_payment_journey():
    sandbox = PaymentSandbox()
    sandbox.execute(ActionType.REGISTER_CUSTOMER.value, {
        "customer_id": "C2",
        "name": "User2",
        "pan": "PAN2",
        "dob": "1990-01-01",
        "address": "X",
        "trust_score": 0.9,
        "verified": True,
        "account_age_days": 400,
    })
    obs = sandbox.execute(ActionType.INITIATE_PAYMENT.value, {
        "transaction_id": "T2",
        "customer_id": "C2",
        "amount": 45000,
        "payment_path": "risk_only",
        "attack_family": "SEP-001",
        "genai_features": {"social_engineering_score": 0.8},
    })
    steps = [j.step for j in obs.journey]
    assert "Gateway/Processor" in steps
    assert "AML/Compliance" in steps
    assert "Risk" in steps
    print(f"expanded journey: {steps}")


if __name__ == "__main__":
    test_all_families_simulatable()
    test_entry_points()
    test_sep_plan_has_genai_and_payment()
    test_ag_plan_cross_stage()
    test_payment_paths()
    test_genai_context_sandbox()
    test_risk_only_payment()
    test_genai_kb_engine_ag001()
    test_lifecycle_registry_covers_stages()
    test_expanded_payment_journey()
    print("\nAll KB wiring + sandbox routing tests passed.")
