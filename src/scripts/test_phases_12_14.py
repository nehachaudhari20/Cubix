#!/usr/bin/env python3
"""Phases 12–14: failure analysis, graph signals, graph model eval."""

import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.blue_team.evaluation.graph_model import run_graph_fidelity, run_graph_model_eval
from backend.blue_team.evaluation.context import EvaluationContext
from backend.blue_team.evaluation_runner import EvaluationRunner
from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.blue_team.features import FeatureBuilder
from backend.blue_team.graph.entity_graph import EntityGraphBuilder
from backend.blue_team.graph.graph_signals import GraphSignalBuilder
from backend.blue_team.schemas import EvidenceRecord
from backend.labs.failure_analysis import FailureAnalysisAggregator, resolve_trigger_to_ctl
from backend.sandbox.state import SandboxState, SyntheticBeneficiary, SyntheticCustomer, SyntheticDevice


def _seed_state() -> SandboxState:
    state = SandboxState()
    now = datetime.now()
    state.customers["C1"] = SyntheticCustomer(
        "C1", "Alice", "PAN1", "1990-01-01", "City", created_at=now - timedelta(days=90)
    )
    state.customers["C2"] = SyntheticCustomer(
        "C2", "Bob", "PAN2", "1991-02-02", "City", created_at=now - timedelta(days=60)
    )
    state.devices["D1"] = SyntheticDevice("D1", "C1", {}, now - timedelta(days=30), now)
    state.devices["D2"] = SyntheticDevice("D2", "C2", {}, now - timedelta(days=20), now)
    state.beneficiaries["B1"] = SyntheticBeneficiary("B1", "C1", "Ben", "acc1", now - timedelta(days=5))
    txs = [
        {"customer_id": "C1", "device_id": "D1", "beneficiary_id": "B1", "amount": 1000, "timestamp": now - timedelta(hours=2)},
        {"customer_id": "C2", "device_id": "D2", "beneficiary_id": "B1", "amount": 2000, "timestamp": now - timedelta(hours=1)},
        {"customer_id": "C1", "device_id": "D1", "beneficiary_id": "B1", "amount": 5000, "timestamp": now - timedelta(minutes=30)},
    ]
    for tx in txs:
        state.add_transaction(tx)
    return state


def test_phase13_graph_signals():
    state = _seed_state()
    tx = {"customer_id": "C1", "device_id": "D1", "beneficiary_id": "B1", "amount": 8000}
    signals = GraphSignalBuilder(state).build(tx)
    assert signals["distinct_beneficiaries_last_24h"] >= 1
    assert signals["beneficiary_distinct_payer_count"] == 2
    assert signals["graph_cluster_size"] >= 2

    row = FeatureBuilder().build(tx, state)
    assert row["distinct_beneficiaries_last_24h"] >= 1
    assert "mule_risk_score" in row

    clusters = EntityGraphBuilder(state).find_cross_account_clusters()
    assert len(clusters) >= 1
    print(f"13 graph signals: payers={signals['beneficiary_distinct_payer_count']} clusters={len(clusters)}")


def test_phase12_failure_analysis():
    records = [
        EvidenceRecord(
            evidence_id="e1",
            campaign_id="camp1",
            attack_family="GP-001",
            action_type="initiate_payment",
            sandbox_decision="ALLOW",
            evasion_outcome="bypassed",
            control_triggers=["CTL-0009"],
            label=1,
            features={"amount": 5000},
            timestamp="2026-08-01T00:00:00Z",
        ),
        EvidenceRecord(
            evidence_id="e2",
            campaign_id="camp2",
            attack_family="AUT-001",
            action_type="initiate_payment",
            sandbox_decision="BLOCK",
            evasion_outcome="blocked",
            control_triggers=["velocity_exceeds_5_24h"],
            blocking_control="Risk",
            label=1,
            features={"amount": 9000},
            timestamp="2026-08-01T00:00:00Z",
        ),
    ]
    gap_report = {
        "control_gaps": 1,
        "total_findings": 1,
        "unique_missing_controls": ["CTL-0105"],
        "findings": [{
            "missing_control_ids": ["CTL-0105"],
            "expected_control_ids": ["CTL-0105", "CTL-0009"],
            "control_gap_detected": True,
        }],
    }
    summaries = [{"family_id": "GP-001", "control_gaps": 1, "steps_executed": 3, "outcomes": ["success"]}]

    report = FailureAnalysisAggregator().aggregate(
        buffer_records=records,
        control_gap_report=gap_report,
        campaign_summaries=summaries,
    )
    assert resolve_trigger_to_ctl("velocity_exceeds_5_24h") == "CTL-0013"
    assert "CTL-0009" in report["ctl_heatmap"]
    assert "CTL-0105" in report["ctl_heatmap"]
    assert len(report["per_family_asr"]) == 2
    assert report["red_eval"]["sandbox_bypass_count"] == 1
    print(f"12 failure analysis: ctl_keys={len(report['ctl_heatmap'])} families={len(report['per_family_asr'])}")


def _graph_record(eid: str, family: str, **features) -> EvidenceRecord:
    base = {
        "amount": 5000,
        "is_shared_beneficiary": 1,
        "beneficiary_distinct_payer_count": 4,
        "graph_cluster_size": 5,
        "mule_risk_score": 0.5,
        "shared_device_customer_count": 2,
    }
    base.update(features)
    return EvidenceRecord(
        evidence_id=eid,
        campaign_id="camp-graph",
        attack_family=family,
        action_type="initiate_payment",
        sandbox_decision="BLOCK",
        evasion_outcome="blocked",
        label=1,
        features=base,
        timestamp="2026-08-01T00:00:00Z",
    )


def test_phase14_graph_model_eval():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features_v3.json")):
        v3 = os.path.join(model_dir, "features_v2.json")
        if not os.path.exists(v3):
            print("SKIP 14: no v3/v2 model")
            return
    with tempfile.TemporaryDirectory() as tmp:
        buffer = EvidenceBuffer(os.path.join(tmp, "evidence.jsonl"))
        buffer.append(_graph_record("g1", "GP-001"))
        buffer.append(_graph_record("g2", "AUT-001", is_shared_beneficiary=0, graph_cluster_size=1))
        runner = EvaluationRunner(model_dir=model_dir, buffer_path=buffer.path)
        try:
            ctx = EvaluationContext.build(runner.evaluator, runner.model_dir, "v1", "v3")
        except FileNotFoundError:
            ctx = EvaluationContext.build(runner.evaluator, runner.model_dir, "v1", "v2")
        gf = run_graph_fidelity(ctx)
        gm = run_graph_model_eval(ctx)
        assert gf.buffer_samples == 2
        assert gm.buffer_samples == 2
        assert gm.composite_cross_account_count >= 1
        print(
            f"14 graph eval: heavy={gf.graph_heavy_count} "
            f"recall_lift={gm.graph_recall_lift:.4f} composites={gm.composite_cross_account_count}"
        )


def test_runner_includes_phases_12_14():
    model_dir = os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models")
    if not os.path.exists(os.path.join(model_dir, "features.json")):
        print("SKIP runner 12-14")
        return
    with tempfile.TemporaryDirectory() as tmp:
        buffer_path = os.path.join(tmp, "evidence.jsonl")
        buffer = EvidenceBuffer(buffer_path)
        buffer.append(_graph_record("r1", "GP-001"))
        out = os.path.join(tmp, "evaluation_report.json")
        runner = EvaluationRunner(model_dir=model_dir, buffer_path=buffer_path)
        try:
            report = runner.run(
                before_version="v1",
                after_version="v3",
                n_baseline_legit=100,
                n_baseline_fraud=100,
                save_path=out,
                failure_analysis={"ctl_heatmap": {"CTL-0009": {"gap_count": 1}}},
            )
        except FileNotFoundError:
            report = runner.run(
                before_version="v1",
                after_version="v2",
                n_baseline_legit=100,
                n_baseline_fraud=100,
                save_path=out,
            )
        assert report.graph_fidelity.buffer_samples >= 1
        assert "13_graph_fidelity" in report.summary["pillars"]
        assert "14_graph_model" in report.summary["pillars"]
        print("runner 12-14: graph pillars wired")


if __name__ == "__main__":
    test_phase13_graph_signals()
    test_phase12_failure_analysis()
    test_phase14_graph_model_eval()
    test_runner_includes_phases_12_14()
    print("\nAll Phases 12-14 tests passed.")
