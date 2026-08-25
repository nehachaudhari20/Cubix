#!/usr/bin/env python3
"""Tests for data-driven RuleEngine + journey correlation + control gaps."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader
from backend.sandbox import PaymentSandbox, ActionType
from backend.sandbox.rules.control_compiler import ControlCompiler
from backend.sandbox.rules.rule_engine import RuleEngine
from backend.sandbox.rules.journey_correlation import build_journey_features
from backend.sandbox.rules.feature_context import build_rule_context
from backend.sandbox.schemas import JourneyStep


def test_rules_loaded_from_kb():
    kb = CanonicalKnowledgeLoader()
    assert len(kb.rules) >= 300, f"expected ~301 rules, got {len(kb.rules)}"
    signal_rules = [r for r in kb.rules if r.get("rule_type") == "signal"]
    assert len(signal_rules) == 276
    composites = [r for r in kb.rules if r.get("rule_type") == "composite"]
    assert len(composites) >= 6
    print(f"KB rules: {len(kb.rules)} (signal={len(signal_rules)}, composite={len(composites)})")


def test_rule_engine_boot_thresholds_from_bindings():
    compiled = ControlCompiler().compile()
    engine = RuleEngine(compiled_controls=compiled)
    # Thresholds must resolve via parameter_bindings / compiled thresholds
    tier1 = engine.resolve_threshold("amount_limit_tier1", "payment_initiation", None)
    assert tier1 is not None and tier1 > 0
    vel = engine.resolve_threshold("velocity_limit_24h", "payment_initiation", None)
    assert vel is not None
    stats = engine.stats()
    assert stats["total"] >= 300
    print(f"RuleEngine boot: {stats} tier1={tier1} velocity={vel}")


def test_composite_and_signal_triggers():
    compiled = ControlCompiler().compile()
    engine = RuleEngine(compiled_controls=compiled)
    ctx = {
        "amount": 60000,
        "is_new_device": True,
        "trust_score": 0.2,
        "verified": True,
        "account_age_days": 10,
        "transaction_count_last_24h": 2,
        "is_new_beneficiary": False,
        "merchant_risk_score": 0.4,
        "family_signal_ids": ["SIG-0001", "SIG-0002"],
        "signal_context_active": True,
        "journey_flag_engines": 0,
        "journey_early_block": False,
        "journey_gateway_flag_count": 0,
        "genai_load_bearing_flag": False,
        "device_age_days": 1,
        "is_unknown_device": False,
        "synthetic_identity_flag": False,
        "round_amount_flag": False,
        "shared_beneficiary_payers": 0,
    }
    result = engine.evaluate(ctx, expected_controls=["CTL-0105", "CTL-0096", "CTL-0172"])
    assert result.risk_contribution > 0
    assert any("amount" in t or "composite" in t or "new_device" in t for t in result.triggered_rules)
    assert "control_gaps" in result.__dataclass_fields__ or result.control_gaps is not None
    print(
        f"composite/signal: risk={result.risk_contribution} "
        f"triggers={len(result.triggered_rules)} gaps={result.control_gaps.get('gap_count')}"
    )


def test_control_gap_detection():
    gaps = RuleEngine.detect_control_gaps(
        triggered_controls=["CTL-0105"],
        expected_controls=["CTL-0105", "CTL-0096", "CTL-0172"],
    )
    assert gaps["has_gap"] is True
    assert "CTL-0096" in gaps["missing_controls"]
    assert gaps["coverage"] < 1.0
    print(f"control gaps: missing={gaps['missing_controls']} coverage={gaps['coverage']}")


def test_journey_correlation_features():
    journey = [
        JourneyStep(step="Device", result={"status": "PASS", "flags": ["new_device"]}),
        JourneyStep(step="Gateway/Processor", result={"status": "PASS", "flags": ["gateway_velocity_burst"]}),
        JourneyStep(step="AML/Compliance", result={"status": "PASS", "flags": ["aml_structuring_proxy"]}),
    ]
    feats = build_journey_features(journey, control_triggers=["CTL-0096"])
    assert feats["journey_flag_engines"] == 3
    assert feats["journey_gateway_flag_count"] >= 1
    assert feats["engine_transition_risk"] > 0
    print(f"journey features: {feats['journey_flag_engines']} engines flagged, risk={feats['engine_transition_risk']}")


def test_sandbox_payment_uses_rule_engine():
    sandbox = PaymentSandbox()
    sandbox.execute(
        ActionType.REGISTER_CUSTOMER.value,
        {
            "customer_id": "C_rules",
            "name": "Rules User",
            "pan": "SYN999",
            "dob": "1990-01-01",
            "address": "X",
            "trust_score": 0.25,
            "verified": True,
            "account_age_days": 5,
        },
    )
    sandbox.execute(
        ActionType.REGISTER_DEVICE.value,
        {"device_id": "D_rules", "customer_id": "C_rules"},
    )
    obs = sandbox.execute(
        ActionType.INITIATE_PAYMENT.value,
        {
            "transaction_id": "T_rules",
            "customer_id": "C_rules",
            "device_id": "D_rules",
            "amount": 75000,
            "payment_path": "full",
            "is_new_device": True,
            "attack_family": "AG-001",
            "expected_controls": ["CTL-0105", "CTL-0096", "CTL-0236"],
            "genai_features": {"genai_load_bearing_flag": 1.0, "prompt_injection_risk": 0.9},
        },
    )
    assert obs.decision in ("ALLOW", "CHALLENGE", "BLOCK")
    assert obs.risk_score is not None
    gaps = (obs.state_snapshot or {}).get("control_gaps")
    journey_feats = (obs.state_snapshot or {}).get("journey_features")
    print(
        f"sandbox payment: decision={obs.decision} risk={obs.risk_score} "
        f"triggers={len(obs.control_triggers or [])} gaps={bool(gaps)} journey={bool(journey_feats)}"
    )
    assert gaps is not None or obs.rule_risk is not None


if __name__ == "__main__":
    test_rules_loaded_from_kb()
    test_rule_engine_boot_thresholds_from_bindings()
    test_composite_and_signal_triggers()
    test_control_gap_detection()
    test_journey_correlation_features()
    test_sandbox_payment_uses_rule_engine()
    print("\nAll RuleEngine upgrade tests passed.")
