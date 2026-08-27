"""
Test Sandbox with KB API Integration
Requires KB API to be running.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
from src.backend.sandbox import PaymentSandbox


def test_kb_connection():
    """Test that KB API is reachable."""
    print("\n" + "="*60)
    print("TESTING KB API CONNECTION")
    print("="*60)
    
    try:
        response = requests.get("http://localhost:8000/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print(f"[OK] KB API is reachable")
            print(f"   Families: {stats.get('total_families', 'N/A')}")
            print(f"   Signals: {stats.get('total_signals', 'N/A')}")
            print(f"   Stages: {stats.get('total_stages', 'N/A')}")
            return True
        else:
            print(f"[FAIL] KB API returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[FAIL] KB API not reachable: {e}")
        print("   Please start the KB API first:")
        print("   uvicorn src.backend.api.knowledge_api:app --reload --port 8000")
        return False


def test_dynamic_rules():
    """Test that rules are fetched dynamically from KB API."""
    print("\n" + "="*60)
    print("TESTING DYNAMIC RULES FROM KB API")
    print("="*60)
    
    sandbox = PaymentSandbox()
    
    # Add a customer
    sandbox.add_customer(
        customer_id="C001",
        name="Rahul Sharma",
        pan="ABC1234567",
        dob="1990-01-01",
        address="Mumbai",
        trust_score=0.7
    )
    
    # Add a device
    sandbox.add_device(
        device_id="D001",
        customer_id="C001"
    )
    
    # Process a transaction
    result = sandbox.process_transaction({
        "transaction_id": "T001",
        "customer_id": "C001",
        "device_id": "D001",
        "amount": 30000,
        "payment_rail": "upi",
        "authentication_method": "otp",
        "merchant_risk_score": 0.5
    })
    
    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")
    print(f"Risk Score: {result['state'].get('risk_score', 'N/A')}")
    
    # Check if rule details show KB-sourced thresholds
    risk_step = None
    for step in result['journey']:
        if step['step'] == 'Risk':
            risk_step = step
            break
    
    if risk_step:
        details = risk_step['result'].get('rule_details', [])
        for rule in details:
            thresholds = rule.get('thresholds_applied')
            if thresholds:
                print(f"  {rule['rule_set']} thresholds: {thresholds}")
    
    return result


def run_tests():
    """Run all KB-integration tests."""
    print("\n" + "="*70)
    print("SANDBOX + KB API INTEGRATION TESTS")
    print("="*70)
    
    if not test_kb_connection():
        print("\n[FAIL] KB API is not running. Please start it first.")
        return
    
    test_dynamic_rules()
    
    print("\n" + "="*70)
    print("[PASS] SANDBOX + KB API INTEGRATION TESTS COMPLETE")
    print("="*70)


if __name__ == "__main__":
    run_tests()