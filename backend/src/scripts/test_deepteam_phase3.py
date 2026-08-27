#!/usr/bin/env python3
"""Phase 3: CVSS prioritization, Control Gap Lab, Hard Negatives."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")

from backend.red_team.agents.strategy_layer import StrategyLayer
from backend.red_team.agents.memory_agent import MemoryAgent
from backend.red_team.agents.threat_hunter import ThreatHunter
from backend.red_team.agents.failure_analyzer import FailureAnalyzer
from backend.red_team.schemas import ActionPayload, AttackPlan, PlanStep
from backend.labs.control_gap import ControlGapLab
from backend.blue_team.hard_negatives import HardNegativeGenerator
from backend.blue_team.evidence_buffer import EvidenceBuffer


def test_cvss_strategy():
    memory = MemoryAgent()
    strategy = StrategyLayer(memory)
    ranked = strategy.prioritized_candidates(set())
    assert ranked, "Expected CVSS-ranked families"
    assert ranked[0].cvss.composite >= ranked[-1].cvss.composite
    decision = strategy.decide(iteration=0, max_iterations=5)
    assert decision.action == "continue"
    assert decision.next_hypothesis is not None
    assert "CVSS" in decision.reason
    print(f"CVSS top family: {ranked[0].family_id} score={ranked[0].cvss.composite}")
    print(f"Strategy: {decision.reason[:80]}...")


def test_threat_hunter_cvss():
    hunter = ThreatHunter()
    output = hunter.discover(tested_families=[])
    assert output.hypotheses
    print(f"ThreatHunter hypotheses: {[h.primary_family for h in output.hypotheses[:3]]}")


def test_control_gap_lab():
    lab = ControlGapLab()
    family = {"attack_id": "AUT-001", "targeted_control_ids": ["CTL-0105", "CTL-0013"]}
    verdict = lab.analyze(
        payload={"amount": 50000, "customer_id": "C1"},
        sandbox_response={"decision": "ALLOW", "control_triggers": ["CTL-0096"]},
        family=family,
    )
    assert verdict.control_gap_detected
    assert "CTL-0105" in verdict.missing_control_ids
    print(f"Control gap missing: {verdict.missing_control_ids}")


def test_failure_analyzer_gap():
    analyzer = FailureAnalyzer()
    plan = AttackPlan(
        campaign_name="test",
        objective="test",
        target_stages=["Authorization"],
        primary_family="AUT-001",
        selected_variant="default",
        steps=[PlanStep(step=1, action_type="initiate_payment", action="pay",
                         target_control="Amount", payload_template={"amount": 50000},
                         expected_outcome="ALLOW", rationale="test")],
        success_criteria="ALLOW",
        estimated_complexity="low",
        reasoning="test",
    )
    payload = ActionPayload(
        action_type="initiate_payment",
        action_payload={"amount": 50000, "customer_id": "C1"},
        step=1, total_steps=1, is_final=True,
        campaign_id="c1", attack_family="AUT-001",
        target_control="Amount", expected_outcome="ALLOW",
    )
    family = analyzer.kb.get_family("AUT-001")
    if family and family.get("targeted_control_ids"):
        result = analyzer.analyze(
            {"decision": "ALLOW", "control_triggers": [], "journey": []},
            payload,
            plan,
        )
        print(f"Analyzer gap detected: {result.control_gap_detected}")
    else:
        print("Analyzer gap: skipped (family missing targeted_control_ids)")


def test_hard_negatives():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "hn.jsonl")
        os.environ["HARD_NEGATIVE_BUFFER_PATH"] = path
        gen = HardNegativeGenerator(buffer=EvidenceBuffer(path))
        records = gen.generate(count=2)
        print(f"Hard negatives generated: {len(records)}")
        if records:
            assert records[0].label == 0
            assert records[0].is_hard_negative


def main() -> int:
    test_cvss_strategy()
    test_threat_hunter_cvss()
    test_control_gap_lab()
    test_failure_analyzer_gap()
    test_hard_negatives()
    print("OK: Phase 3 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
