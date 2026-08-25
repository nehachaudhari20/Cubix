#!/usr/bin/env python3
"""Smoke test ControlCompiler + compiled sandbox boot + deepteam schemas."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.sandbox.rules.control_compiler import ControlCompiler
from backend.sandbox import PaymentSandbox
from backend.red_team.deepteam.schemas import CVSSScore, JailbreakStrategy
from backend.red_team.deepteam.cvss_scorer import score_family, prioritize_attacks
from backend.red_team.deepteam.jailbreak_planner import JailbreakPlanner
from backend.red_team.deepteam.attack_engine import PaymentAttackEngine
from backend.knowledge.loader import KnowledgeLoader


def main() -> int:
    compiler = ControlCompiler()
    errors = compiler.validate_refs()
    assert not errors, errors

    compiled = compiler.compile()
    stats = compiled.stats()
    print("ControlCompiler")
    print(f"  controls: {stats['controls']}")
    print(f"  parameter_bindings: {stats['parameter_bindings']}")
    print(f"  trigger_mappings: {stats['trigger_mappings']}")

    assert compiled.resolve_trigger("amount_exceeds_25000") == "CTL-0105"
    assert compiled.resolve_trigger("velocity_exceeds_5_24h") == "CTL-0013"

    sandbox = PaymentSandbox(compiled_controls=compiled)
    sandbox.execute("register_customer", {
        "customer_id": "C_TEST",
        "name": "Test User",
        "pan": "SYN0000001",
        "dob": "1990-01-01",
        "address": "Test City",
        "trust_score": 0.7,
        "verified": True,
    })
    sandbox.execute("register_device", {
        "device_id": "D_TEST",
        "customer_id": "C_TEST",
        "fingerprint": {"browser": "Chrome"},
    })
    obs = sandbox.execute("initiate_payment", {
        "transaction_id": "txn_test_1",
        "customer_id": "C_TEST",
        "device_id": "D_TEST",
        "amount": 30000,
        "payment_rail": "UPI",
        "authentication_method": "otp",
        "merchant_risk_score": 0.3,
    })
    print(f"Sandbox payment decision: {obs.decision}")
    print(f"  control_triggers (KB IDs): {obs.control_triggers[:5]}")

    loader = KnowledgeLoader()
    family = loader.get_family("AUT-001") or loader.families[0]
    planner = JailbreakPlanner()
    crescendo = planner.plan(family, JailbreakStrategy.CRESCENDO)[0]
    print(f"JailbreakPlanner crescendo steps: {len(crescendo.steps)}")

    engine = PaymentAttackEngine(compiled_controls=compiled)
    result = engine.generate(
        {"amount": 30000},
        {"customer_id": "C_TEST", "device_id": "D_TEST", "amount": 5000, "payment_rail": "UPI"},
    )
    print(f"PaymentAttackEngine valid variations: {result.valid_count}")

    candidate = score_family(
        family.get("attack_id", "X"),
        family.get("name", "X"),
        potential_amount=35000,
        step_count=len(crescendo.steps),
        bypass_probability=0.4,
        strategy=JailbreakStrategy.CRESCENDO,
    )
    ranked = prioritize_attacks([candidate])
    print(f"CVSS composite: {ranked[0].cvss.composite}")

    print("OK: Phase 0 + Phase 1 smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
