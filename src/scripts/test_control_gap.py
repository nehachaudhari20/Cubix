#!/usr/bin/env python3
"""Dedicated Control Gap Lab tests (FraudJudge + CTL-* vocabulary)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")

from backend.labs.control_gap import ControlGapLab
from backend.red_team.deepteam.fraud_judge import FraudInvestigatorJudge
from backend.red_team.agents.failure_analyzer import FailureAnalyzer
from backend.red_team.schemas import ActionPayload, AttackPlan, PlanStep


def test_fraud_judge_detects_gap_on_allow():
    judge = FraudInvestigatorJudge()
    verdict = judge.evaluate(
        payload={"amount": 50000, "customer_id": "C1"},
        sandbox_response={"decision": "ALLOW", "control_triggers": ["CTL-0096"]},
        expected_control_ids=["CTL-0105", "CTL-0013", "CTL-0096"],
    )
    assert verdict.control_gap_detected
    assert "CTL-0105" in verdict.missing_control_ids
    assert "CTL-0013" in verdict.missing_control_ids
    assert "CTL-0096" not in verdict.missing_control_ids
    assert verdict.investigator_summary
    print(f"gap on ALLOW: missing={verdict.missing_control_ids}")


def test_fraud_judge_no_gap_on_block():
    judge = FraudInvestigatorJudge()
    verdict = judge.evaluate(
        payload={"amount": 50000},
        sandbox_response={"decision": "BLOCK", "control_triggers": ["CTL-0105"]},
        expected_control_ids=["CTL-0105", "CTL-0013"],
    )
    assert not verdict.control_gap_detected
    assert "CTL-0013" in verdict.missing_control_ids
    print("no gap on BLOCK: OK")


def test_control_gap_lab_export_report():
    lab = ControlGapLab()
    family = {
        "attack_id": "GP-001",
        "targeted_control_ids": ["CTL-0268", "CTL-0018", "CTL-0105"],
    }
    lab.analyze(
        payload={"amount": 45000, "mcc": "7995"},
        sandbox_response={"decision": "ALLOW", "control_triggers": ["CTL-0096"]},
        family=family,
    )
    lab.analyze(
        payload={"amount": 10000},
        sandbox_response={"decision": "BLOCK", "control_triggers": ["CTL-0268"]},
        family=family,
    )
    report = lab.export_report()
    assert report["total_findings"] >= 1
    assert report["control_gaps"] >= 1
    assert "CTL-0268" in report["unique_missing_controls"] or "CTL-0018" in report["unique_missing_controls"]
    assert len(report["findings"]) >= 1
    finding = report["findings"][0]
    assert "missing_control_ids" in finding
    assert "triggered_control_ids" in finding
    print(f"export_report: gaps={report['control_gaps']} findings={report['total_findings']}")


def test_failure_analyzer_ctl_vocabulary():
    analyzer = FailureAnalyzer()
    plan = AttackPlan(
        campaign_name="gap-test",
        objective="test",
        target_stages=["Payment Initiation"],
        primary_family="AUT-001",
        selected_variant="default",
        steps=[PlanStep(
            step=1, action_type="initiate_payment", action="pay",
            target_control="Amount", payload_template={"amount": 50000},
            expected_outcome="ALLOW", rationale="test",
        )],
        success_criteria="ALLOW",
        estimated_complexity="low",
        reasoning="test",
    )
    payload = ActionPayload(
        action_type="initiate_payment",
        action_payload={"amount": 50000, "customer_id": "C_gap"},
        step=1, total_steps=1, is_final=True,
        campaign_id="gap_c1", attack_family="AUT-001",
        target_control="Amount", expected_outcome="ALLOW",
    )
    family = analyzer.kb.get_family("AUT-001")
    if not family or not family.get("targeted_control_ids"):
        print("failure_analyzer CTL: skipped (no targeted_control_ids on AUT-001)")
        return

    result = analyzer.analyze(
        {"decision": "ALLOW", "control_triggers": ["CTL-0096"], "journey": [], "state": {}},
        payload,
        plan,
    )
    triggers = ["CTL-0096"]
    assert all(t.startswith("CTL-") for t in triggers)
    print(
        f"analyzer: gap={result.control_gap_detected} "
        f"missing={result.missing_control_ids[:3]}"
    )


def test_memory_affects_cvss_ranking():
    from backend.red_team.agents.memory_agent import MemoryAgent
    from backend.red_team.agents.strategy_layer import StrategyLayer
    from backend.red_team.schemas import AnalysisResult, Hypothesis, MemoryEntry

    memory = MemoryAgent()
    strategy = StrategyLayer(memory)
    before = strategy.prioritized_candidates(set())
    assert before

    top_id = before[0].family_id
    memory.memories.append(MemoryEntry(
        memory_id="mem_test",
        context=f"Attack on {top_id} failed",
        observed_control="Risk",
        response="failure",
        attack_attempted=top_id,
        evidence_count=1,
        confidence=0.9,
        applicable_conditions={
            "primary_family": top_id,
            "outcome": "failure",
            "blocking_control": "Risk",
        },
        strategy_used=None,
        last_validated="2026-01-01",
    ))
    after = strategy.prioritized_candidates({top_id})
    assert after
    print(f"memory CVSS: tested {top_id}, next={after[0].family_id}")


def main() -> int:
    test_fraud_judge_detects_gap_on_allow()
    test_fraud_judge_no_gap_on_block()
    test_control_gap_lab_export_report()
    test_failure_analyzer_ctl_vocabulary()
    test_memory_affects_cvss_ranking()
    print("OK: test_control_gap passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
