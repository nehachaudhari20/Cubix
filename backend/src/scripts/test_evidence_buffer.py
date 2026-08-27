"""
Step 5B — Evidence buffer tests.

Run:
  python src/scripts/test_evidence_buffer.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("USE_KB_API", "false")
os.environ.setdefault("FRAUDSHIELD_ENABLED", "false")

from backend.blue_team.evidence_buffer import EvidenceBuffer
from backend.blue_team.collector import EvidenceCollector
from backend.red_team.sandbox_client import SandboxClient
from backend.red_team.agents.attack_planner import AttackPlanner
from backend.red_team.agents.attack_generator import AttackGenerator
from backend.red_team.agents.failure_analyzer import FailureAnalyzer
from backend.red_team.agents.threat_hunter import ThreatHunter
from backend.red_team.agent_helpers import OfflineKnowledge
from backend.red_team.graph import RedTeamGraph


def test_collector_stores_payment_evidence():
    print("\n" + "=" * 60)
    print("TEST 1: EvidenceCollector — payment step stored")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "evidence.jsonl")
        buffer = EvidenceBuffer(path)
        collector = EvidenceCollector(buffer=buffer)
        client = SandboxClient()

        kb = OfflineKnowledge()
        family = kb.get_family("CM-001")
        hunter = ThreatHunter()
        hypothesis = hunter.hypothesis_from_family(family)
        plan = AttackPlanner().plan(hypothesis)
        sequence = AttackGenerator().generate_sequence(plan)
        analyzer = FailureAnalyzer()

        stored = 0
        for payload in sequence.payloads:
            response = client.execute_payload(payload.model_dump())
            analysis = analyzer.analyze(response, payload, plan)
            record = collector.collect(
                sandbox_response=response,
                payload=payload,
                plan=plan,
                hypothesis=hypothesis,
                analysis=analysis,
                sandbox=client.get_sandbox(),
            )
            if record:
                stored += 1
                print(f"  Stored {record.evidence_id}: {record.action_type} → {record.sandbox_decision} ({record.evasion_outcome})")

        stats = buffer.stats()
        assert stats["payment_records"] == stored
        assert stats["payment_records"] >= 1
        assert stats["fraud_labeled"] == stats["payment_records"]
        assert all(r.label == 1 for r in buffer.read_all())
        print(f"  Buffer stats: {stats['payment_records']} payments, {stats['bypassed']} bypassed, {stats['blocked']} blocked")
        print("  ✅ PASSED")


def test_export_training_rows():
    print("\n" + "=" * 60)
    print("TEST 2: EvidenceBuffer — export for retraining")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "evidence.jsonl")
        buffer = EvidenceBuffer(path)
        collector = EvidenceCollector(buffer=buffer)
        client = SandboxClient()

        family = OfflineKnowledge().get_family("AUT-001")
        hypothesis = ThreatHunter().hypothesis_from_family(family)
        plan = AttackPlanner().plan(hypothesis)
        sequence = AttackGenerator().generate_sequence(plan)

        for payload in sequence.payloads:
            if payload.action_type != "initiate_payment":
                continue
            response = client.execute_payload(payload.model_dump())
            analysis = FailureAnalyzer().analyze(response, payload, plan)
            collector.collect(response, payload, plan, hypothesis, analysis, client.get_sandbox())

        rows = buffer.export_training_rows()
        assert len(rows) >= 1
        assert rows[0]["is_fraud"] == 1
        assert "amount" in rows[0]
        assert rows[0]["source"] == "adversarial_buffer"
        print(f"  Exported {len(rows)} training rows with {len(rows[0])} fields")
        print("  ✅ PASSED")


def test_graph_feeds_buffer():
    print("\n" + "=" * 60)
    print("TEST 3: RedTeamGraph — auto-collects evidence")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "evidence.jsonl")
        os.environ["EVIDENCE_BUFFER_PATH"] = path
        os.environ["EVIDENCE_BUFFER_ENABLED"] = "true"

        graph = RedTeamGraph()
        graph.run(max_iterations=1)

        stats = graph.evidence_collector.buffer.stats()
        assert stats["total"] >= 1, f"Expected evidence in buffer, got {stats}"
        print(f"  Graph collected {stats['payment_records']} payment records")
        print(f"  Families: {stats['families']}")
        print("  ✅ PASSED")


def main():
    print("Evidence Buffer Tests (Step 5B)")
    test_collector_stores_payment_evidence()
    test_export_training_rows()
    test_graph_feeds_buffer()
    print("\n" + "=" * 60)
    print("ALL EVIDENCE BUFFER TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
