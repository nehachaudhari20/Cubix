"""
Exercise Red Team agents and print outputs — verify Cohere LLM wiring.

Usage:
  python src/scripts/test_red_team_llm_agents.py
  python src/scripts/test_red_team_llm_agents.py --family AUT-001
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
os.chdir(ROOT)
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


def print_payload_preview(action_type: str, payload: dict, max_len: int = 400) -> None:
    text = json.dumps(payload, default=str)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    print(f"    {action_type}: {text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Red Team agent outputs with LLM")
    parser.add_argument(
        "--family",
        help="KB attack_id for fallback hypothesis if Threat Hunter returns none",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    kb = OfflineKnowledge()

    if not args.json:
        sep("LLM CONFIG")
        print(json.dumps(llm_status(), indent=2))
        print(f"  use_llm() = {use_llm()}")
        if not use_llm_enabled():
            print("\nWARNING: RED_TEAM_USE_LLM is not true — agents will use rule-based fallbacks.")

    # 1. Threat Hunter (LLM when enabled) — composites + GenAI/CVSS
    hunter = ThreatHunter()
    hunt = hunter.discover(
        memory_context="Prior run: velocity block on AF families",
        tested_families=[],
        prefer_composites=True,
        max_hypotheses=5,
    )
    if args.json:
        dump("threat_hunter", hunt, True)
    else:
        sep(f"1. THREAT HUNTER (LLM={'yes' if use_llm() else 'KB fallback'})")
        dump("ThreatHunterOutput", hunt, False)

    if hunt.hypotheses:
        hypothesis = hunt.hypotheses[0]
    elif args.family:
        family = kb.get_family(args.family)
        if not family:
            raise SystemExit(f"Family not found: {args.family}")
        hypothesis = hunter.hypothesis_from_family(family)
    else:
        simulatable = kb.get_simulatable_families()
        if not simulatable:
            raise SystemExit("No simulatable families in KB")
        hypothesis = hunter.hypothesis_from_family(simulatable[0])

    hyp_family = hypothesis.primary_family
    if not args.json:
        print(f"\n  Selected hypothesis: {hypothesis.name}")
        print(f"  primary={hyp_family}  composites={hypothesis.composite_families or []}")
        if len(hunt.hypotheses) > 1:
            print(f"  queue ({len(hunt.hypotheses)} total):")
            for h in hunt.hypotheses:
                print(f"    - {h.primary_family} + {h.composite_families or []}")

    # 2. Attack Planner — LLM path (no jailbreak strategy)
    planner = AttackPlanner()
    if not args.json:
        sep(f"2. ATTACK PLANNER — LLM path (hypothesis.primary_family={hyp_family})")

    os.environ.pop("RED_TEAM_JAILBREAK_STRATEGY", None)
    llm_plan = planner.plan(hypothesis)
    if args.json:
        dump("attack_planner_llm", llm_plan, True)
    else:
        dump("AttackPlan (LLM or KB)", llm_plan, False)
        print(f"  primary_family: {llm_plan.primary_family}")
        print(f"  jailbreak_strategy: {llm_plan.jailbreak_strategy}")
        payment_steps = [s for s in llm_plan.steps if s.action_type == "initiate_payment"]
        print(f"  payment_steps: {len(payment_steps)}")
        for s in payment_steps[:3]:
            print(f"    step {s.step}: {s.action} template={s.payload_template}")

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

    # 4. Attack Generator — full concrete payloads (all engine variations)
    os.environ.setdefault("RED_TEAM_ENGINE_EXECUTE_ALL", "true")
    os.environ.setdefault("RED_TEAM_ENGINE_MAX_VARIATIONS", "20")
    generator = AttackGenerator()
    sequence = generator.generate_sequence(llm_plan)
    if args.json:
        dump("attack_generator", sequence, True)
    else:
        sep("4. ATTACK GENERATOR (concrete payloads + all variations)")
        print(f"  payloads: {len(sequence.payloads)}")
        by_type: dict[str, int] = {}
        rails: dict[str, int] = {}
        for p in sequence.payloads:
            by_type[p.action_type] = by_type.get(p.action_type, 0) + 1
            if p.action_type == "initiate_payment":
                rail = str((p.action_payload or {}).get("payment_rail") or "?")
                rails[rail] = rails.get(rail, 0) + 1
        print(f"  action_mix: {by_type}")
        print(f"  payment_rails: {rails}")
        # Print setup steps + a sample of payment variations
        shown = 0
        for p in sequence.payloads:
            if p.action_type != "initiate_payment" or shown < 5:
                print(f"  step {p.step}/{p.total_steps} [{p.action_type}] {p.variation_label or ''}")
                print_payload_preview(p.action_type, p.action_payload)
                if p.action_type == "initiate_payment":
                    shown += 1
        pay_n = by_type.get("initiate_payment", 0)
        if pay_n > 5:
            print(f"  ... +{pay_n - 5} more payment variations")

    # 5. Failure Analyzer on REAL sandbox output (not mock risk)
    from backend.red_team.sandbox_client import SandboxClient

    analyzer = FailureAnalyzer()
    client = SandboxClient()
    sandbox_response = None
    sample_payload = None
    # Prefer a payment payload; fall back to last
    for p in sequence.payloads:
        if p.action_type == "initiate_payment":
            sample_payload = p
            break
    if sample_payload is None and sequence.payloads:
        sample_payload = sequence.payloads[-1]

    analysis = None
    if sample_payload:
        # Execute prior setup steps so payment has state
        for p in sequence.payloads:
            if p.step >= sample_payload.step:
                break
            if p.action_type != "initiate_payment":
                client.execute_payload(p.model_dump())
        sandbox_response = client.execute_payload(sample_payload.model_dump())
        analysis = analyzer.analyze(sandbox_response, sample_payload, llm_plan)
        if args.json:
            dump("sandbox_response", sandbox_response, True)
            dump("failure_analyzer", analysis, True)
        else:
            sep(f"5. FAILURE ANALYZER (real sandbox, LLM={'yes' if use_llm() else 'rule-based'})")
            print(
                f"  sandbox decision={sandbox_response.get('decision')} "
                f"risk_score={sandbox_response.get('risk_score')} "
                f"ml_score={sandbox_response.get('ml_score')} "
                f"triggers={sandbox_response.get('control_triggers')}"
            )
            dump("AnalysisResult", analysis, False)

    # 6. Payment Attack Engine — expanded variation space
    engine = PaymentAttackEngine()
    sample_payment = (sample_payload.action_payload if sample_payload else None) or {
        "amount": 45000,
        "hour": 2,
        "beneficiary_id": "BEN_NEW_001",
        "payment_rail": "card",
    }
    variation_set = engine.generate(
        {
            "amount": sample_payment.get("amount"),
            "beneficiary_id": sample_payment.get("beneficiary_id"),
            "payment_rail": sample_payment.get("payment_rail"),
        },
        sample_payment,
    )
    if args.json:
        dump("attack_engine", variation_set, True)
    else:
        sep(f"6. PAYMENT ATTACK ENGINE (LLM validate={'yes' if use_llm() else 'pass-through'})")
        print(
            f"  variations: {variation_set.valid_count} valid / "
            f"{variation_set.attempted_count} attempted"
        )
        for v in variation_set.variations[:12]:
            rail = (v.action_payload or {}).get("payment_rail")
            amt = (v.action_payload or {}).get("amount")
            reason = f" — {v.validation_reason}" if v.validation_reason else ""
            print(f"    - {v.label}: {v.validation_status} amount={amt} rail={rail}{reason}")
        if variation_set.attempted_count > 12:
            print(f"    ... +{variation_set.attempted_count - 12} more")

    # 7. Fraud Investigator Judge on real sandbox response
    judge = FraudInvestigatorJudge()
    if sandbox_response is None:
        sandbox_response = {
            "decision": "UNKNOWN",
            "control_triggers": [],
            "risk_score": None,
        }
    triggered = list(sandbox_response.get("control_triggers") or [])
    expected = triggered[:1] + ["amount_limit_tier2", "velocity_burst"]
    expected = list(dict.fromkeys(expected))
    verdict = judge.evaluate(
        payload=sample_payment,
        sandbox_response=sandbox_response,
        expected_control_ids=expected,
        triggered_control_ids=triggered,
    )
    if args.json:
        dump("fraud_judge", verdict, True)
    else:
        sep(f"7. FRAUD INVESTIGATOR JUDGE (real sandbox, LLM={'yes' if use_llm() else 'template'})")
        print(f"  sandbox risk_score={sandbox_response.get('risk_score')}")
        dump("FraudJudgeVerdict", verdict, False)

    # 8. Strategy Layer — mutate current before CVSS jump
    memory = MemoryAgent()
    strategy = StrategyLayer(memory)
    if analysis is not None:
        memory.store_analysis(analysis, hypothesis, {})
    last = analysis.model_dump() if analysis is not None else {
        "outcome": "failure",
        "blocking_control": "Risk",
        "mutation_suggestions": ["Reduce amount below risk tier threshold"],
        "risk_score": sandbox_response.get("risk_score"),
    }
    decision = strategy.decide(
        current_hypothesis=hypothesis,
        last_analysis=last,
        iteration=1,
        max_iterations=5,
    )
    coverage = strategy.coverage_report()
    if args.json:
        dump("strategy_decision", decision, True)
        dump("strategy_coverage", coverage, True)
    else:
        sep("8. STRATEGY LAYER (mutate-before-jump)")
        dump("StrategyDecision", decision, False)
        print(f"  action={decision.action}")
        print(f"  threat_hunter picked: {hyp_family} + {hypothesis.composite_families or []}")
        nxt = decision.next_hypothesis
        if nxt:
            print(
                f"  next: {nxt.primary_family} + {nxt.composite_families or []} "
                f"strategy={nxt.jailbreak_strategy}"
            )
        print(f"  coverage: tested={coverage['tested']} remaining={coverage['remaining']}")

    if not args.json:
        sep("DONE")
        if use_llm():
            print("LLM agents exercised. Sections 5/7 use REAL sandbox risk_score.")
        else:
            print("Set RED_TEAM_USE_LLM=true to test live Cohere outputs.")


if __name__ == "__main__":
    main()
