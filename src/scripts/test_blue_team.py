"""
Blue Team + FraudShield tests.

Run:
  python src/scripts/test_blue_team.py

Train model first (once):
  python src/scripts/train_model.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("USE_KB_API", "false")
os.environ.setdefault("RED_TEAM_USE_LLM", "false")

from backend.blue_team.features import FeatureBuilder
from backend.blue_team.fraudshield import load_fraudshield, DEFAULT_MODEL_DIR
from backend.sandbox import PaymentSandbox


def test_feature_builder():
    print("\n" + "=" * 60)
    print("TEST 1: FeatureBuilder — sandbox → feature vector")
    print("=" * 60)

    sandbox = PaymentSandbox()
    sandbox.add_customer("C_bt1", "Test User", "PAN123", "1990-01-01", "City", trust_score=0.7)
    sandbox.add_device("D_bt1", "C_bt1", {"browser": "Chrome"})

    fb = FeatureBuilder()
    row = fb.build(
        {"customer_id": "C_bt1", "device_id": "D_bt1", "amount": 5000, "payment_rail": "upi"},
        sandbox.get_state(),
    )
    assert row["amount"] == 5000
    assert row["payment_rail"] == "upi"
    assert "device_age_days" in row
    print(f"  Built {len(row)} features")
    print(f"  amount={row['amount']}, velocity_score={row['velocity_score']}")
    print("  ✅ PASSED")


def test_fraudshield_load():
    print("\n" + "=" * 60)
    print("TEST 2: FraudShieldModel — load from data/models")
    print("=" * 60)

    model = load_fraudshield()
    if model is None:
        print(f"  ⚠️  No model at {DEFAULT_MODEL_DIR}/features.json")
        print("  Run: python src/scripts/train_model.py")
        print("  SKIPPED (model not trained yet)")
        return None

    print(f"  Loaded: {model.model_type} v{model.version}")
    print(f"  Features: {len(model.feature_order)}")
    print(f"  Threshold: {model.threshold}")
    print("  ✅ PASSED")
    return model


def test_sandbox_with_fraudshield(model):
    print("\n" + "=" * 60)
    print("TEST 3: Sandbox Risk Engine — real ML score")
    print("=" * 60)

    if model is None:
        print("  SKIPPED (no model)")
        return

    sandbox = PaymentSandbox(ml_model=model)
    sandbox.add_customer("C_bt2", "User", "PAN456", "1990-01-01", "City", trust_score=0.8)
    sandbox.add_device("D_bt2", "C_bt2")

    legit = sandbox.process_transaction({
        "transaction_id": "T_legit",
        "customer_id": "C_bt2",
        "device_id": "D_bt2",
        "amount": 2000,
        "payment_rail": "upi",
        "authentication_method": "otp",
        "merchant_risk_score": 0.2,
    })

    fraud_attempt = sandbox.process_transaction({
        "transaction_id": "T_fraud",
        "customer_id": "C_bt2",
        "device_id": "D_bt2",
        "amount": 75000,
        "payment_rail": "upi",
        "authentication_method": "otp",
        "merchant_risk_score": 0.8,
    })

    legit_ml = legit.get("state", {}).get("ml_score")
    fraud_ml = fraud_attempt.get("state", {}).get("ml_score")

    print(f"  Legit ₹2000:  decision={legit['decision']}  ml_score={legit_ml}")
    print(f"  High ₹75000:  decision={fraud_attempt['decision']}  ml_score={fraud_ml}")

    assert legit_ml is not None, "ml_score should be set when FraudShield loaded"
    assert legit_ml != 0.3 or fraud_ml != 0.3, "Should not be hardcoded 0.3 stub"
    print("  ✅ PASSED")


def test_fraudshield_prediction(model):
    print("\n" + "=" * 60)
    print("TEST 4: FraudShield predict() — full metadata")
    print("=" * 60)

    if model is None:
        print("  SKIPPED (no model)")
        return

    sandbox = PaymentSandbox()
    sandbox.add_customer("C_bt3", "User", "PAN789", "1990-01-01", "City")
    sandbox.add_device("D_bt3", "C_bt3")

    pred = model.predict(
        {"customer_id": "C_bt3", "device_id": "D_bt3", "amount": 15000, "payment_rail": "upi"},
        sandbox.get_state(),
    )
    print(f"  fraud_probability: {pred.fraud_probability}")
    print(f"  is_fraud_predicted: {pred.is_fraud_predicted}")
    print(f"  features_used: {len(pred.features_used)}")
    print("  ✅ PASSED")


def main():
    print("Blue Team + FraudShield Tests")
    test_feature_builder()
    model = test_fraudshield_load()
    test_sandbox_with_fraudshield(model)
    test_fraudshield_prediction(model)

    print("\n" + "=" * 60)
    if model:
        print("ALL BLUE TEAM TESTS PASSED ✅")
    else:
        print("PARTIAL PASS — train model to enable full ML tests")
    print("=" * 60)


if __name__ == "__main__":
    main()
