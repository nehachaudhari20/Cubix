#!/usr/bin/env python3
"""Tests for PaymentAttackEngine (Transform -> Vary -> Validate)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")

from backend.red_team.deepteam.attack_engine import PaymentAttackEngine
from backend.red_team.deepteam.schemas import MutationPayload


def test_transform_applies_mutation_fields():
    engine = PaymentAttackEngine()
    mutation = MutationPayload(amount=12000, hour=14, payment_rail="UPI")
    baseline = {
        "transaction_id": "txn_base",
        "customer_id": "C1",
        "device_id": "D1",
        "amount": 5000,
        "payment_rail": "card",
    }
    merged = engine._transform(baseline, mutation)
    assert merged["amount"] == 12000
    assert merged["hour"] == 14
    assert merged["payment_rail"] == "UPI"
    assert merged["customer_id"] == "C1"
    print("transform: OK")


def test_vary_produces_three_variations():
    engine = PaymentAttackEngine()
    mutation = MutationPayload(amount=10000)
    baseline = {
        "transaction_id": "txn_base",
        "customer_id": "C1",
        "device_id": "D1",
        "amount": 10000,
        "payment_rail": "UPI",
    }
    variations = engine._vary(baseline, mutation)
    labels = {v.label for v in variations}
    assert len(variations) == 3
    assert "amount_2x_threshold" in labels
    assert "timing_2am" in labels
    assert "new_beneficiary" in labels
    print(f"vary labels: {labels}")


def test_generate_validates_without_llm():
    engine = PaymentAttackEngine()
    mutation = MutationPayload(amount=15000, hour=10)
    legitimate = {
        "transaction_id": "txn_test",
        "customer_id": "C_test",
        "device_id": "D_test",
        "amount": 8000,
        "payment_rail": "UPI",
        "authentication_method": "otp",
    }
    result = engine.generate(mutation, legitimate)
    assert result.valid_count >= 1
    assert len(result.variations) >= 1
    for var in result.variations:
        assert var.validation_status == "VALID"
        assert "amount" in var.action_payload
    print(f"generate: {result.valid_count} valid variations")


def test_cvss_scorer_integration():
    from backend.red_team.deepteam.cvss_scorer import score_family, prioritize_attacks
    from backend.red_team.deepteam.schemas import JailbreakStrategy

    high = score_family(
        "AUT-001", "Auth manipulation",
        potential_amount=50000, step_count=3, bypass_probability=0.6,
        strategy=JailbreakStrategy.LINEAR,
    )
    low = score_family(
        "AML-001", "AML probe",
        potential_amount=5000, step_count=8, bypass_probability=0.2,
        strategy=JailbreakStrategy.LINEAR,
    )
    ranked = prioritize_attacks([low, high])
    assert ranked[0].family_id == "AUT-001"
    assert ranked[0].cvss.composite >= ranked[1].cvss.composite
    print(f"CVSS rank: {ranked[0].family_id}({ranked[0].cvss.composite}) > {ranked[1].family_id}")


def main() -> int:
    test_transform_applies_mutation_fields()
    test_vary_produces_three_variations()
    test_generate_validates_without_llm()
    test_cvss_scorer_integration()
    print("OK: test_deepteam_attack_engine passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
