"""
Continuous Red Team campaign runner (KB -> Planner -> Generator -> Sandbox).

Used by test scripts and loop_runner. No LLM/Bedrock required by default.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .agent_helpers import OfflineKnowledge
from .kb_campaign_builder import classify_family, is_simulatable
from .agents.threat_hunter import ThreatHunter
from .agents.attack_planner import AttackPlanner
from .agents.attack_generator import AttackGenerator
from .agents.failure_analyzer import FailureAnalyzer
from .agents.strategy_layer import StrategyLayer
from .agents.memory_agent import MemoryAgent
from .sandbox_client import SandboxClient
from .deepteam.linear_mutator import LinearMutator


def _linear_retry_limit() -> int:
    try:
        return max(0, int(os.environ.get("RED_TEAM_LINEAR_RETRIES", "2")))
    except ValueError:
        return 2


def select_families(
    kb: OfflineKnowledge,
    *,
    max_families: int = 5,
    family_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if family_id:
        family = kb.get_family(family_id)
        return [family] if family else []

    memory = MemoryAgent()
    strategy = StrategyLayer(memory)
    ranked = strategy.prioritized_candidates(set())
    families: List[Dict[str, Any]] = []
    for candidate in ranked:
        family = kb.get_family(candidate.family_id)
        if family and is_simulatable(family):
            families.append(family)
        if len(families) >= max_families:
            break
    if not families:
        families = kb.get_simulatable_families()[:max_families]
    return families


def run_family_campaign(
    family: dict,
    hunter: ThreatHunter,
    planner: AttackPlanner,
    generator: AttackGenerator,
    client: SandboxClient,
    analyzer: FailureAnalyzer,
    mutator: LinearMutator,
    *,
    print_sections: bool = True,
) -> dict:
    """Run one KB family through Red Team -> Sandbox with optional linear retries."""
    strategy = os.environ.get("RED_TEAM_JAILBREAK_STRATEGY", "kb")
    hypothesis = hunter.hypothesis_from_family(family)
    hypothesis.jailbreak_strategy = strategy
    plan = planner.plan(hypothesis)
    sequence = generator.generate_sequence(plan)

    if print_sections:
        _print_red_team_section(family, hypothesis, plan, sequence)

    results: List[Dict[str, Any]] = []
    last_analysis = None
    linear_limit = _linear_retry_limit()

    if print_sections:
        _sep(f"SANDBOX OUTPUT - {family.get('attack_id')}", char="-")

    for payload in sequence.payloads:
        payloads_to_run = [payload]
        if payload.action_type == "initiate_payment" and linear_limit > 0:
            pass

        for current in payloads_to_run:
            response = client.execute_payload(current.model_dump())
            if print_sections:
                _print_sandbox_step(current.step, current.action_type, response, current)

            analysis = analyzer.analyze(response, current, plan)
            results.append({
                "step": current.step,
                "action_type": current.action_type,
                "decision": response.get("decision"),
                "triggers": response.get("control_triggers"),
                "outcome": analysis.outcome,
                "variation": current.variation_label,
                "linear": "linear" in (current.variation_label or ""),
            })
            last_analysis = analysis

            if (
                current.action_type == "initiate_payment"
                and analysis.outcome == "failure"
                and linear_limit > 0
            ):
                for attempt in range(linear_limit):
                    mutated = mutator.mutate(current, analysis, attempt=attempt)
                    response = client.execute_payload(mutated.model_dump())
                    if print_sections:
                        _print_sandbox_step(
                            mutated.step, mutated.action_type, response, mutated, retry=attempt + 1
                        )
                    analysis = analyzer.analyze(response, mutated, plan)
                    results.append({
                        "step": mutated.step,
                        "action_type": mutated.action_type,
                        "decision": response.get("decision"),
                        "triggers": response.get("control_triggers"),
                        "outcome": analysis.outcome,
                        "variation": mutated.variation_label,
                        "linear": True,
                    })
                    last_analysis = analysis
                    if analysis.outcome == "success":
                        break

    if print_sections and last_analysis:
        _print_analysis_section(last_analysis)

    return {
        "family_id": family.get("attack_id"),
        "strategy": plan.jailbreak_strategy,
        "steps_executed": len(results),
        "payloads_generated": sequence.total_payloads,
        "final_decision": results[-1]["decision"] if results else None,
        "outcomes": [r["outcome"] for r in results],
        "linear_retries_used": sum(1 for r in results if r.get("linear")),
    }


def run_continuous(
    max_families: int = 5,
    family_id: Optional[str] = None,
    *,
    print_sections: bool = True,
) -> List[dict]:
    kb = OfflineKnowledge()
    hunter = ThreatHunter()
    planner = AttackPlanner()
    generator = AttackGenerator()
    client = SandboxClient()
    analyzer = FailureAnalyzer()
    mutator = LinearMutator()

    if print_sections:
        _print_kb_section(kb)

    families = select_families(kb, max_families=max_families, family_id=family_id)
    if not families:
        print("ERROR: No simulatable families found")
        return []

    if print_sections:
        _sep(f"CONTINUOUS RUN - {len(families)} families (CVSS-ordered)")
        print(f"  strategy={os.environ.get('RED_TEAM_JAILBREAK_STRATEGY', 'kb')}  "
              f"attack_engine={os.environ.get('RED_TEAM_USE_ATTACK_ENGINE', 'true')}  "
              f"linear_retries={_linear_retry_limit()}")

    summary: List[dict] = []
    for i, family in enumerate(families, 1):
        if print_sections:
            print(f"\n{'#' * 72}")
            print(f"# CAMPAIGN {i}/{len(families)}: {family.get('attack_id')} - {family.get('name')}")
            print(f"{'#' * 72}")

        if not is_simulatable(family):
            if print_sections:
                print(f"  SKIPPED (not simulatable: {family.get('simulation_type')})")
            continue

        summary.append(run_family_campaign(
            family, hunter, planner, generator, client, analyzer, mutator,
            print_sections=print_sections,
        ))

    if print_sections:
        _sep("RUN SUMMARY")
        total_payloads = 0
        for s in summary:
            total_payloads += s["steps_executed"]
            successes = s["outcomes"].count("success")
            print(
                f"  {s['family_id']:10s}  strategy={s.get('strategy', 'kb'):10s}  "
                f"generated={s['payloads_generated']}  executed={s['steps_executed']}  "
                f"linear+={s.get('linear_retries_used', 0)}  "
                f"successes={successes}/{len(s['outcomes'])}"
            )
        stats = kb.kb_stats()
        print(f"\n  Total sandbox executions this run: {total_payloads}")
        print(f"  KB: {stats['total_families']} families | {stats['simulatable_families']} simulatable")
        print("\n  OK Dynamic KB -> Red Team -> Sandbox continuous run complete")
        print("  (Bedrock/LLM not required; set RED_TEAM_USE_LLM=true + LLM_PROVIDER=bedrock later)")

    return summary


def _sep(title: str, char: str = "=", width: int = 72) -> None:
    print(f"\n{char * width}\n{title}\n{char * width}")


def _print_kb_section(kb: OfflineKnowledge) -> None:
    _sep("KNOWLEDGE BASE (canonical -> KnowledgeLoader)")
    stats = kb.kb_stats()
    print(f"  families={stats['total_families']}  signals={stats['total_signals']}  stages={stats['total_stages']}")
    print(f"  simulatable={stats['simulatable_families']}")
    memory = MemoryAgent()
    top = StrategyLayer(memory).prioritized_candidates(set())[:5]
    if top:
        print("  CVSS top 5:", ", ".join(f"{c.family_id}({c.cvss.composite})" for c in top))


def _print_red_team_section(family, hypothesis, plan, sequence) -> None:
    _sep(f"RED TEAM - {family.get('attack_id')}")
    print(f"  pattern={classify_family(family)}  strategy={plan.jailbreak_strategy}")
    print(f"  plan steps={len(plan.steps)}  payloads={sequence.total_payloads}")
    for p in sequence.payloads:
        eng = " [engine]" if p.engine_validated else ""
        preview = json.dumps(p.action_payload, default=str)[:80]
        print(f"    [{p.step}/{p.total_steps}] {p.action_type}{eng}: {preview}...")


def _print_sandbox_step(step, action_type, response, payload, retry: int = 0) -> None:
    prefix = f"    Step {step} [{action_type}]"
    if retry:
        prefix += f" linear-retry #{retry}"
    if payload.variation_label:
        prefix += f" ({payload.variation_label})"
    print(prefix)
    print(f"      decision={response.get('decision')}  reason={response.get('reason', '')}")
    triggers = response.get("control_triggers") or []
    if triggers:
        print(f"      triggers={', '.join(triggers[:4])}")


def _print_analysis_section(analysis) -> None:
    print(f"\n  Analyzer: outcome={analysis.outcome.upper()}  blocked={analysis.blocking_control}")
    if analysis.control_gap_detected:
        print(f"  Control gap: missing {analysis.missing_control_ids}")
    if analysis.mutation_suggestions:
        print(f"  Next mutation hint: {analysis.mutation_suggestions[0]}")
