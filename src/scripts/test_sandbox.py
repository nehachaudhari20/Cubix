"""
Sandbox Test Script
Tests all core functionalities of the Payment Sandbox.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.sandbox import PaymentSandbox


def test_legitimate_transaction():
    """Test 1: Legitimate transaction should be ALLOWED."""
    print("\n" + "="*60)
    print("TEST 1: LEGITIMATE TRANSACTION")
    print("="*60)
    
    sandbox = PaymentSandbox()
    
    # Add customer
    sandbox.add_customer(
        customer_id="C001",
        name="Rahul Sharma",
        pan="ABC1234567",
        dob="1990-01-01",
        address="Mumbai",
        trust_score=0.8
    )
    
    # Add device
    sandbox.add_device(
        device_id="D001",
        customer_id="C001",
        fingerprint={"browser": "Chrome", "os": "Windows"}
    )
    
    # Process transaction
    result = sandbox.process_transaction({
        "transaction_id": "T001",
        "customer_id": "C001",
        "device_id": "D001",
        "amount": 5000,
        "payment_rail": "upi",
        "authentication_method": "otp",
        "merchant_risk_score": 0.2
    })
    
    print(f"Transaction ID: {result['transaction_id']}")
    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")
    print(f"Journey Steps: {len(result['journey'])}")
    
    # Verify expected outcome
    assert result["decision"] == "ALLOW", f"Expected ALLOW, got {result['decision']}"
    print("[PASS] Test 1: Legitimate transaction allowed")
    return result


def test_fraudulent_transaction():
    """Test 2: Fraudulent transaction (high amount + new device) should be BLOCKED."""
    print("\n" + "="*60)
    print("TEST 2: FRAUDULENT TRANSACTION")
    print("="*60)
    
    sandbox = PaymentSandbox()
    
    # Add customer
    sandbox.add_customer(
        customer_id="C002",
        name="Priya Patel",
        pan="XYZ9876543",
        dob="1985-05-15",
        address="Delhi",
        trust_score=0.6
    )
    
    # No device added — will be unknown
    
    # Process transaction (new device, high amount)
    result = sandbox.process_transaction({
        "transaction_id": "T002",
        "customer_id": "C002",
        "device_id": "D999",  # Unknown device
        "amount": 75000,       # High amount
        "payment_rail": "card",
        "authentication_method": "otp",
        "merchant_risk_score": 0.8
    })
    
    print(f"Transaction ID: {result['transaction_id']}")
    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")
    print(f"Risk Score: {result['state'].get('risk_score', 'N/A')}")
    
    # Verify expected outcome (should be BLOCKED)
    assert result["decision"] == "BLOCK", f"Expected BLOCK, got {result['decision']}"
    print("[PASS] Test 2: Fraudulent transaction blocked")
    return result


def test_velocity_limit():
    """Test 3: Velocity limit should trigger BLOCK after 5+ transactions."""
    print("\n" + "="*60)
    print("TEST 3: VELOCITY LIMIT")
    print("="*60)
    
    sandbox = PaymentSandbox()
    
    # Add customer
    sandbox.add_customer(
        customer_id="C003",
        name="Amit Kumar",
        pan="DEF4567890",
        dob="1992-03-20",
        address="Bangalore",
        trust_score=0.7
    )
    
    # Add device
    sandbox.add_device(
        device_id="D003",
        customer_id="C003"
    )
    
    # Send 6 transactions quickly
    results = []
    for i in range(6):
        result = sandbox.process_transaction({
            "transaction_id": f"T003_{i}",
            "customer_id": "C003",
            "device_id": "D003",
            "amount": 1000,
            "payment_rail": "upi",
            "authentication_method": "otp",
            "merchant_risk_score": 0.2
        })
        results.append(result)
        print(f"Transaction {i+1}: {result['decision']}")
    
    # Check last transaction (should be BLOCKED)
    last_result = results[-1]
    assert last_result["decision"] == "BLOCK", f"Expected BLOCK, got {last_result['decision']}"
    assert last_result["reason"] == "velocity_exceeded", f"Expected velocity_exceeded, got {last_result['reason']}"
    
    print("[PASS] Test 3: Velocity limit triggered block")
    return results


def test_unknown_customer():
    """Test 4: Unknown customer should be BLOCKED."""
    print("\n" + "="*60)
    print("TEST 4: UNKNOWN CUSTOMER")
    print("="*60)
    
    sandbox = PaymentSandbox()
    
    # No customer added
    
    # Process transaction with unknown customer
    result = sandbox.process_transaction({
        "transaction_id": "T004",
        "customer_id": "C999",  # Unknown
        "device_id": "D004",
        "amount": 1000,
        "payment_rail": "upi",
        "authentication_method": "otp"
    })
    
    print(f"Transaction ID: {result['transaction_id']}")
    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")
    
    # Verify
    assert result["decision"] == "BLOCK", f"Expected BLOCK, got {result['decision']}"
    assert result["reason"] == "kyc_failed", f"Expected kyc_failed, got {result['reason']}"
    
    print("[PASS] Test 4: Unknown customer blocked")
    return result


def test_journey_tracking():
    """Test 5: Full journey tracking should capture all steps."""
    print("\n" + "="*60)
    print("TEST 5: JOURNEY TRACKING")
    print("="*60)
    
    sandbox = PaymentSandbox()
    
    sandbox.add_customer(
        customer_id="C005",
        name="Sneha Reddy",
        pan="GHI7890123",
        dob="1988-07-10",
        address="Hyderabad",
        trust_score=0.5
    )
    
    sandbox.add_device(
        device_id="D005",
        customer_id="C005"
    )
    
    result = sandbox.process_transaction({
        "transaction_id": "T005",
        "customer_id": "C005",
        "device_id": "D005",
        "amount": 15000,
        "payment_rail": "upi",
        "authentication_method": "otp",
        "merchant_risk_score": 0.4
    })
    
    print(f"Decision: {result['decision']}")
    print(f"Journey Steps:")
    for step in result['journey']:
        print(f"  → {step['step']}: {step['result'].get('status', step['result'].get('decision', 'N/A'))}")
    
    # Verify all expected steps are present
    expected_steps = ["KYC", "Device", "Authentication", "Payment Initiation", "Risk", "Authorization"]
    if result["decision"] == "ALLOW":
        expected_steps.append("Settlement")
    
    actual_steps = [step['step'] for step in result['journey']]
    print(f"\nExpected steps: {expected_steps}")
    print(f"Actual steps: {actual_steps}")
    
    for step in expected_steps:
        assert step in actual_steps, f"Missing step: {step}"
    
    print("[PASS] Test 5: Full journey tracked")
    return result


def test_state_persistence():
    """Test 6: State should persist across transactions."""
    print("\n" + "="*60)
    print("TEST 6: STATE PERSISTENCE")
    print("="*60)
    
    sandbox = PaymentSandbox()
    
    sandbox.add_customer(
        customer_id="C006",
        name="Vikram Singh",
        pan="JKL4567890",
        dob="1980-12-01",
        address="Chandigarh",
        trust_score=0.7
    )
    
    sandbox.add_device(
        device_id="D006",
        customer_id="C006"
    )
    
    # First transaction
    result1 = sandbox.process_transaction({
        "transaction_id": "T006_1",
        "customer_id": "C006",
        "device_id": "D006",
        "amount": 1000,
        "payment_rail": "upi",
        "authentication_method": "otp"
    })
    print(f"Transaction 1: {result1['decision']}")
    
    # Check customer state
    customer = sandbox.get_state().get_customer("C006")
    print(f"Customer {customer.customer_id} has {len(customer.transactions)} transactions")
    assert len(customer.transactions) == 1, "Customer should have 1 transaction"
    
    # Second transaction
    result2 = sandbox.process_transaction({
        "transaction_id": "T006_2",
        "customer_id": "C006",
        "device_id": "D006",
        "amount": 2000,
        "payment_rail": "upi",
        "authentication_method": "otp"
    })
    print(f"Transaction 2: {result2['decision']}")
    
    # Check customer state again
    customer = sandbox.get_state().get_customer("C006")
    print(f"Customer {customer.customer_id} now has {len(customer.transactions)} transactions")
    assert len(customer.transactions) == 2, "Customer should have 2 transactions"
    
    print("[PASS] Test 6: State persisted correctly")
    return result1, result2


def test_multi_step_merchant_payment():
    """Test 7: Multi-step flow — register, merchant, beneficiary, pay."""
    print("\n" + "="*60)
    print("TEST 7: MULTI-STEP MERCHANT PAYMENT")
    print("="*60)

    sandbox = PaymentSandbox()

    sandbox.add_customer("C007", "Arjun Mehta", "JKL111", "1991-01-01", "Pune", trust_score=0.8)
    sandbox.add_device("D007", "C007")
    sandbox.open_account("ACC007", "C007", balance=100000)
    sandbox.onboard_merchant("M007", "Honest Grocery", mcc="5411", kyb_verified=True, risk_score=0.2)
    sandbox.link_beneficiary("BEN007", "C007", name="Supplier Co")

    result = sandbox.process_transaction({
        "transaction_id": "T007",
        "customer_id": "C007",
        "device_id": "D007",
        "account_id": "ACC007",
        "merchant_id": "M007",
        "beneficiary_id": "BEN007",
        "amount": 8000,
        "payment_rail": "upi",
        "authentication_method": "otp",
    })

    print(f"Decision: {result['decision']}")
    steps = [s["step"] for s in result["journey"]]
    print(f"Journey: {steps}")

    assert result["decision"] == "ALLOW", f"Expected ALLOW, got {result['decision']}"
    assert "Payment Initiation" in steps
    assert sandbox.get_state().get_merchant("M007") is not None
    assert sandbox.get_state().get_beneficiary("BEN007") is not None

    print("[PASS] Test 7: Multi-step merchant payment succeeded")
    return result


def test_mcc_misrepresentation_blocks():
    """Test 8: MCC misrepresentation raises merchant risk and can block high-value tx."""
    print("\n" + "="*60)
    print("TEST 8: MCC MISREPRESENTATION")
    print("="*60)

    sandbox = PaymentSandbox()

    sandbox.add_customer("C008", "Fraud Merchant Owner", "MCC999", "1985-01-01", "Delhi", trust_score=0.6)
    sandbox.add_device("D008", "C008")
    sandbox.onboard_merchant(
        "M008", "Fake Retail", mcc="7995", declared_mcc="5411",
        kyb_verified=True, risk_score=0.3,
    )

    result = sandbox.process_transaction({
        "transaction_id": "T008",
        "customer_id": "C008",
        "device_id": "D008",
        "merchant_id": "M008",
        "amount": 45000,
        "payment_rail": "card",
        "authentication_method": "otp",
    })

    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")
    print(f"Risk Score: {result['state'].get('risk_score')}")

    assert result["decision"] in ("BLOCK", "CHALLENGE"), f"Expected BLOCK/CHALLENGE, got {result['decision']}"
    pi_step = next(s for s in result["journey"] if s["step"] == "Payment Initiation")
    assert "mcc_misrepresentation" in pi_step["result"].get("flags", [])

    print("[PASS] Test 8: MCC misrepresentation detected and blocked/challenged")
    return result


def test_invalid_payment_amount():
    """Test 9: Zero amount fails at payment initiation."""
    print("\n" + "="*60)
    print("TEST 9: INVALID PAYMENT AMOUNT")
    print("="*60)

    sandbox = PaymentSandbox()
    sandbox.add_customer("C009", "Test User", "INV009", "1990-01-01", "Chennai", trust_score=0.8)
    sandbox.add_device("D009", "C009")

    result = sandbox.process_transaction({
        "transaction_id": "T009",
        "customer_id": "C009",
        "device_id": "D009",
        "amount": 0,
        "payment_rail": "upi",
        "authentication_method": "otp",
    })

    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")

    assert result["decision"] == "BLOCK"
    assert result["reason"] == "payment_initiation_failed"

    print("[PASS] Test 9: Invalid amount blocked at payment initiation")
    return result


def run_all_tests():
    """Run all sandbox tests."""
    print("\n" + "="*70)
    print("RUNNING SANDBOX TESTS")
    print("="*70)
    
    try:
        test_legitimate_transaction()
        test_fraudulent_transaction()
        test_velocity_limit()
        test_unknown_customer()
        test_journey_tracking()
        test_state_persistence()
        test_multi_step_merchant_payment()
        test_mcc_misrepresentation_blocks()
        test_invalid_payment_amount()
        
        print("\n" + "="*70)
        print("ALL SANDBOX TESTS PASSED")
        print("="*70)
        print("\nSummary:")
        print("  - Legitimate transactions -> ALLOW")
        print("  - Fraudulent transactions -> BLOCK")
        print("  - Velocity limits enforced")
        print("  - Unknown customers blocked")
        print("  - Full journey tracked")
        print("  - State persists across transactions")
        print("  - Multi-step merchant/beneficiary payments work")
        print("  - MCC misrepresentation detected")
        print("  - Invalid payments blocked at initiation")
        
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()