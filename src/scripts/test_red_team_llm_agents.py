"""
Exercise Red Team agents and print outputs — verify Cohere LLM wiring.

Usage:
  python src/scripts/test_red_team_llm_agents.py
  python src/scripts/test_red_team_llm_agents.py --family AF-001
  python src/scripts/test_red_team_llm_agents.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(os.path.dirname(ROOT))
load_dotenv()

from backend.llm import llm_status, use_llm_enabled  # noqa: E402
from backend.red_team.agent_helpers import OfflineKnowledge, use_llm  # noqa: E402
from backend.red_team.agents.threat_hunter import ThreatHunter  # noqa: E402
from backend.red_team.agents.attack_planner import AttackPlanner  # noqa: E402
from backend.red_team.agents.attack_generator import AttackGenerator  # noqa: E402
from backend.red_team.agents.failure_analyzer import FailureAnalyzer  # noqa: E402
from backend.red_team.agents.memory_agent import MemoryAgent  # noqa: E402
from backend.red_team.agents.strategy_layer import StrategyLayer  # noqa: E402
from backend.red_team.deepteam.attack_engine import PaymentAttackEngine  # noqa: E402
from backend.red_team.deepteam.fraud_judge import FraudInvestigatorJudge  # noqa: E402
from backend.red_team.deepteam.schemas import JailbreakStrategy  # noqa: E402
from backend.red_team.schemas import Hypothesis  # noqa: E402


def sep(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def dump(label: str, obj: Any, as_json: bool) -> None:
    if as_json:
        if hasattr(obj, "model_dump"):
            payload = obj.model_dump()
        else:
            payload = obj
        print(json.dumps({label: payload}, indent=2, default=str))
        return
    print(f"\n--- {label} ---")
    if hasattr(obj, "model_dump_json"):
        print(obj.model_dump_json(indent=2))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            dump(f"{label}[{i}]", item, as_json=False)
    else:
        print(json.dumps(obj, indent=2, default=str))


def pick_family(kb: OfflineKnowledge, family_id: str | None) -> dict:
    if family_id:
        family = kb.get_family(family_id)
        if not family:
            raise SystemExit(f"Family not found: {family_id}")
        return family
    simulatable = kb.get_simulatable_families()
    if not simulatable:
        raise SystemExit("No simulatable families in KB")
    return simulatable[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Red Team agent outputs with LLM")
    parser.add_argument("--family", help="KB attack_id to use for planner/analyzer tests")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    kb = OfflineKnowledge()
    family = pick_family(kb, args.family)
    family_id = family["attack_id"]

    if not args.json:
        sep("LLM CONFIG")
        print(json.dumps(llm_status(), indent=2))
        print(f"  use_llm() = {use_llm()}")
        if not use_llm_enabled():
            print("\nWARNING: RED_TEAM_USE_LLM is not true — agents will use rule-based fallbacks.")

    # 1. Threat Hunter (LLM when enabled)
    hunter = ThreatHunter()
    hunt = hunter.discover(memory_context="Prior run: velocity block on AF families", tested_families=[])
    if args.json:
        dump("threat_hunter", hunt, True)
    else:
        sep(f"1. THREAT HUNTER (LLM={'yes' if use_llm() else 'KB fallback'})")
        dump("ThreatHunterOutput", hunt, False)

    hypothesis = hunt.hypotheses[0] if hunt.hypotheses else hunter.hypothesis_from_family(family)

    # 2. Attack Planner — LLM path (no jailbreak strategy)
    planner = AttackPlanner()
    if args.json:
        pass
    else:
        sep(f"2. ATTACK PLANNER — LLM path (family={family_id})")

    os.environ.pop("RED_TEAM_JAILBREAK_STRATEGY", None)
    llm_plan = planner.plan(hypothesis)
    if args.json:
        dump("attack_planner_llm", llm_plan, True)
    else:
        dump("AttackPlan (LLM or KB)", llm_plan, False)
        print(f"  jailbreak_strategy: {llm_plan.jailbreak_strategy}")

    # 3. Jailbreak strategies (rule-based DeepTeam planners)
    if not args.json:
        sep("3. JAILBREAK PLANS (rule-based — Crescendo / Tree / Sequential)")
    for strategy in (JailbreakStrategy.CRESCENDO, JailbreakStrategy.TREE, JailbreakStrategy.SEQUENTIAL):
        hyp = hypothesis.model_copy(update={"jailbreak_strategy": strategy.value})
        branches = planner.plan_branches(hyp)
        if args.json:
            dump(f"jailbreak_{strategy.value}", branches, True)
        else:
            print(f"\n  Strategy: {strategy.value} → {len(branches)} branch(es)")
            for b in branches[:2]:
                print(f"    - {b.campaign_name} ({len(b.steps)} steps)")

    # 4. Attack Generator
    generator = AttackGenerator()
    sequence = generator.generate_sequence(llm_plan)
    if args.json:
        dump("attack_generator", sequence, True)
    else:
        sep("4. ATTACK GENERATOR (payload builder)")
        print(f"  payloads: {len(sequence.payloads)}")
        for p in sequence.payloads[:3]:
            print(f"    step {p.step}: {p.action_type} → {list(p.action_payload.keys())[:5]}")

    # 5. Failure Analyzer (LLM enhancement when enabled)
    analyzer = FailureAnalyzer()
    sample_payload = sequence.payloads[-1] if sequence.payloads else None
    sandbox_response = {
        "decision": "BLOCK",
        "reason": "velocity_threshold_exceeded",
        "control_triggers": ["velocity_burst", "amount_tier2"],
        "risk_score": 0.82,
    }
    analysis = None
    if sample_payload:
        analysis = analyzer.analyze(sandbox_response, sample_payload, llm_plan)
        if args.json:
            dump("failure_analyzer", analysis, True)
        else:
            sep(f"5. FAILURE ANALYZER (LLM={'yes' if use_llm() else 'rule-based'})")
            dump("AnalysisResult", analysis, False)

    # 6. Payment Attack Engine LLM validator
    engine = PaymentAttackEngine()
    sample_payment = {"amount": 45000, "hour": 2, "beneficiary_id": "BEN_NEW_001"}
    variation_set = engine.generate(
        {"amount": 45000, "beneficiary_id": "BEN_NEW_001"},
        sample_payment,
    )
    if args.json:
        dump("attack_engine", variation_set, True)
    else:
        sep(f"6. PAYMENT ATTACK ENGINE (LLM validate={'yes' if use_llm() else 'pass-through'})")
        print(f"  valid variations: {variation_set.valid_count}/{len(variation_set.variations)}")
        for v in variation_set.variations[:2]:
            print(f"    - {v.label}: {v.validation_status}")

    # 7. Fraud Investigator Judge (LLM)
    judge = FraudInvestigatorJudge()
    verdict = judge.evaluate(
        payload=sample_payment,
        sandbox_response=sandbox_response,
        expected_control_ids=["velocity_burst", "amount_limit_tier2"],
        triggered_control_ids=["velocity_burst"],
    )
    if args.json:
        dump("fraud_judge", verdict, True)
    else:
        sep(f"7. FRAUD INVESTIGATOR JUDGE (LLM={'yes' if use_llm() else 'template'})")
        dump("FraudJudgeVerdict", verdict, False)

    # 8. Strategy Layer + Memory (rule-based CVSS)
    memory = MemoryAgent()
    strategy = StrategyLayer(memory)
    if analysis is not None:
        memory.store_analysis(analysis, hypothesis, {})
    decision = strategy.decide(current_hypothesis=hypothesis, last_analysis=None)
    coverage = strategy.coverage_report()
    if args.json:
        dump("strategy_decision", decision, True)
        dump("strategy_coverage", coverage, True)
    else:
        sep("8. STRATEGY LAYER (CVSS — rule-based, no LLM)")
        dump("StrategyDecision", decision, False)
        print(f"  coverage: tested={coverage['tested']} remaining={coverage['remaining']}")
        print(f"  cvss_top5: {coverage['cvss_top5'][:3]}")

    if not args.json:
        sep("DONE")
        if use_llm():
            print("LLM agents exercised. Review sections 1, 2, 5, 6, 7 for Cohere-generated content.")
        else:
            print("Set RED_TEAM_USE_LLM=true to test live Cohere outputs.")


if __name__ == "__main__":
    main()
