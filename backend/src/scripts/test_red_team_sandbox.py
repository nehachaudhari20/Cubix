"""
Red Team + Sandbox integration tests (no LLM required).
Run: python src/scripts/test_red_team_sandbox.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("USE_KB_API", "false")

from backend.red_team.sandbox_client import SandboxClient
from backend.red_team.agents.threat_hunter import ThreatHunter
from backend.red_team.agents.attack_planner import AttackPlanner
from backend.red_team.agents.attack_generator import AttackGenerator
from backend.red_team.agents.failure_analyzer import FailureAnalyzer
from backend.red_team.schemas import ActionPayload, Hypothesis, AttackPlan
from backend.red_team.graph import RedTeamGraph


def test_sandbox_client_register_and_pay():
    print("\n" + "=" * 60)
    print("TEST 1: SandboxClient — register + payment")
    print("=" * 60)

    client = SandboxClient()
    cid, did = "C_rt1", "D_rt1"

    r1 = client.execute_action("register_customer", {
        "customer_id": cid,
        "name": "Red Team Customer",
        "pan": "RT0000001",
        "dob": "1990-01-01",
        "address": "Test City",
        "trust_score": 0.75,
        "verified": True,
    })
    assert r1["decision"] == "PASS", f"Expected PASS, got {r1['decision']}"
    print(f"  register_customer → {r1['decision']}")

    r2 = client.execute_action("register_device", {
        "device_id": did,
        "customer_id": cid,
        "fingerprint": {"browser": "Chrome"},
    })
    assert r2["decision"] == "PASS"
    print(f"  register_device → {r2['decision']}")

    r3 = client.execute_action("initiate_payment", {
        "transaction_id": "txn_rt1",
        "customer_id": cid,
        "device_id": did,
        "amount": 5000,
        "payment_rail": "upi",
        "authentication_method": "otp",
        "merchant_risk_score": 0.2,
    })
    assert r3["decision"] in ("ALLOW", "CHALLENGE", "BLOCK")
    assert "journey" in r3 and len(r3["journey"]) > 0
    print(f"  initiate_payment → {r3['decision']} ({r3['reason']})")
    print("  ✅ PASSED")


def test_threat_hunter_offline():
    print("\n" + "=" * 60)
    print("TEST 2: ThreatHunter — rule-based hypotheses")
    print("=" * 60)

    hunter = ThreatHunter()
    output = hunter.discover(memory_context="No memories yet.")
    assert len(output.hypotheses) >= 1
    h = output.hypotheses[0]
    assert h.primary_family
    assert h.target_stages
    assert h.attack_flow_summary
    print(f"  Hypothesis: {h.name} ({h.primary_family})")
    print(f"  Flow: {h.attack_flow_summary}")
    print("  ✅ PASSED")
    return h


def test_plan_generate_execute(hypothesis: Hypothesis):
    print("\n" + "=" * 60)
    print("TEST 3: Plan → Generate → Execute (mule campaign)")
    print("=" * 60)

    planner = AttackPlanner()
    generator = AttackGenerator()
    client = SandboxClient()

    plan = planner.plan(hypothesis)
    assert len(plan.steps) >= 3
    print(f"  Plan: {plan.campaign_name} ({len(plan.steps)} steps)")

    sequence = generator.generate_sequence(plan)
    assert sequence.total_payloads == len(plan.steps)
    print(f"  Generated {sequence.total_payloads} actions")

    last_response = None
    for payload in sequence.payloads:
        last_response = client.execute_payload(payload.model_dump())
        print(f"  Step {payload.step} {payload.action_type} → {last_response['decision']}")

    assert last_response is not None
    print("  ✅ PASSED")
    return plan, sequence.payloads[-1], last_response


def test_failure_analyzer(plan: AttackPlan, payload: ActionPayload, response: dict):
    print("\n" + "=" * 60)
    print("TEST 4: FailureAnalyzer — real observation parsing")
    print("=" * 60)

    analyzer = FailureAnalyzer()
    result = analyzer.analyze(response, payload, plan)
    assert result.outcome in ("success", "failure")
    assert len(result.learnings) >= 2
    assert len(result.mutation_suggestions) >= 1
    print(f"  Outcome: {result.outcome}")
    print(f"  Blocking: {result.blocking_control} — {result.blocking_reason}")
    print(f"  Mutations: {result.mutation_suggestions[0]}")
    print("  ✅ PASSED")


def test_full_graph_one_iteration():
    print("\n" + "=" * 60)
    print("TEST 5: RedTeamGraph — one campaign iteration")
    print("=" * 60)

    graph = RedTeamGraph()
    final = graph.run(max_iterations=1)

    assert final.get("payloads") is not None or final.get("analysis") is not None
    assert graph.memory_agent.get_stats()["total_memories"] >= 1
    print(f"  Memories stored: {graph.memory_agent.get_stats()['total_memories']}")
    print(f"  Experiments: {graph.state.experiment_count}")
    print("  ✅ PASSED")


def main():
    print("Red Team + Sandbox Integration Tests")
    print("RED_TEAM_USE_LLM=false (rule-based agents)")

    test_sandbox_client_register_and_pay()
    hypothesis = test_threat_hunter_offline()
    plan, payload, response = test_plan_generate_execute(hypothesis)
    test_failure_analyzer(plan, payload, response)
    test_full_graph_one_iteration()

    print("\n" + "=" * 60)
    print("ALL RED TEAM TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
