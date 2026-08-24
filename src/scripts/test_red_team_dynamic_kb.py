"""
Dynamic KB → Red Team → Sandbox continuous test.

Loads the canonical KB via KnowledgeLoader, dynamically selects simulatable families,
generates campaigns via agents, executes in sandbox, and prints separate
Red Team vs Sandbox output sections.

Run:
  python src/scripts/test_red_team_dynamic_kb.py
  python src/scripts/test_red_team_dynamic_kb.py --families 5
  python src/scripts/test_red_team_dynamic_kb.py --family AUT-001
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("USE_KB_API", "false")

from backend.red_team.agent_helpers import OfflineKnowledge
from backend.red_team.kb_campaign_builder import classify_family, is_simulatable
from backend.red_team.agents.threat_hunter import ThreatHunter
from backend.red_team.agents.attack_planner import AttackPlanner
from backend.red_team.agents.attack_generator import AttackGenerator
from backend.red_team.agents.failure_analyzer import FailureAnalyzer
from backend.red_team.sandbox_client import SandboxClient


def sep(title: str, char: str = "=", width: int = 72):
    print(f"\n{char * width}")
    print(title)
    print(f"{char * width}")


def print_kb_section(kb: OfflineKnowledge):
    sep("SECTION 1: KNOWLEDGE BASE (canonical → KnowledgeLoader)")
    stats = kb.kb_stats()
    print(f"  attack families  → {stats['total_families']} families")
    print(f"  signals          → {stats['total_signals']} signals")
    print(f"  lifecycle stages → {stats['total_stages']} stages")
    print(f"  Simulatable in sandbox → {stats['simulatable_families']} families")
    print(f"\n  Sample simulatable IDs: {', '.join(stats['simulatable_ids'][:12])}...")
    print(f"\n  Sample stage + controls:")
    for stage in kb.stages[:3]:
        controls = (stage.get("controls") or [])[:3]
        print(f"    • {stage.get('stage_name')}: {', '.join(controls)}")


def print_red_team_section(family: dict, hypothesis, plan, sequence):
    sep(f"SECTION 2: RED TEAM OUTPUT — {family.get('attack_id')}")
    print(f"  Family:     {family.get('name')}")
    print(f"  Stage:      {family.get('lifecycle_stage')}")
    print(f"  Sim type:   {family.get('simulation_type')}")
    print(f"  Pattern:    {classify_family(family)}")
    print(f"  Controls:   {', '.join((family.get('controls_targeted') or [])[:3])}")
    signals = family.get("detection_signals") or []
    print(f"  KB signals: {', '.join(s.get('name', '')[:40] for s in signals[:3])}")

    print(f"\n  ── Threat Hunter (Hypothesis) ──")
    print(f"  Name:       {hypothesis.name}")
    print(f"  Family ID:  {hypothesis.primary_family}")
    print(f"  Variant:    {hypothesis.suggested_variant}")
    print(f"  Flow:       {hypothesis.attack_flow_summary[:100]}...")
    print(f"  Reasoning:  {hypothesis.reasoning[:120]}...")

    print(f"\n  ── Attack Planner ({len(plan.steps)} steps) ──")
    print(f"  Campaign:   {plan.campaign_name}")
    print(f"  Objective:  {plan.objective[:100]}...")
    for step in plan.steps:
        tpl_keys = list((step.payload_template or {}).keys())
        print(f"    Step {step.step}: {step.action_type:20s} → {step.target_control}  {tpl_keys}")

    print(f"\n  ── Attack Generator ({sequence.total_payloads} payloads) ──")
    for p in sequence.payloads:
        preview = json.dumps(p.action_payload, default=str)[:90]
        print(f"    [{p.step}/{p.total_steps}] {p.action_type}: {preview}...")


def print_sandbox_section(step_num, action_type, response):
    decision = response.get("decision", "?")
    reason = response.get("reason", "")
    triggers = response.get("control_triggers") or []
    journey = response.get("journey") or []
    journey_str = " → ".join(s.get("step", "?") for s in journey)

    print(f"    Step {step_num} [{action_type}]")
    print(f"      Decision:  {decision} ({reason})")
    if journey:
        print(f"      Journey:   {journey_str}")
    if triggers:
        print(f"      Triggers:  {', '.join(triggers[:5])}")
    risk = (response.get("state") or {}).get("risk_score")
    if risk is not None:
        print(f"      Risk:      {risk}")


def print_analysis_section(analysis):
    print(f"\n  ── Failure Analyzer ──")
    print(f"  Outcome:    {analysis.outcome.upper()}")
    print(f"  Blocked at: {analysis.blocking_control} — {analysis.blocking_reason}")
    for learning in analysis.learnings:
        print(f"    • {learning}")
    if analysis.mutation_suggestions:
        print(f"  Mutations:  {analysis.mutation_suggestions[0]}")


def run_family_campaign(
    family: dict,
    hunter: ThreatHunter,
    planner: AttackPlanner,
    generator: AttackGenerator,
    client: SandboxClient,
    analyzer: FailureAnalyzer,
) -> dict:
    """Run one full KB family through Red Team → Sandbox."""
    hypothesis = hunter.hypothesis_from_family(family)
    plan = planner.plan(hypothesis)
    sequence = generator.generate_sequence(plan)

    print_red_team_section(family, hypothesis, plan, sequence)

    sep(f"SECTION 3: SANDBOX OUTPUT — {family.get('attack_id')}", char="-")
    results = []
    last_analysis = None

    for payload in sequence.payloads:
        response = client.execute_payload(payload.model_dump())
        print_sandbox_section(payload.step, payload.action_type, response)

        analysis = analyzer.analyze(response, payload, plan)
        results.append({
            "step": payload.step,
            "action_type": payload.action_type,
            "decision": response.get("decision"),
            "triggers": response.get("control_triggers"),
            "outcome": analysis.outcome,
        })
        last_analysis = analysis

    print_analysis_section(last_analysis)

    return {
        "family_id": family.get("attack_id"),
        "steps_executed": len(results),
        "final_decision": results[-1]["decision"] if results else None,
        "outcomes": [r["outcome"] for r in results],
    }


def run_continuous(
    max_families: int = 5,
    family_id: str = None,
):
    kb = OfflineKnowledge()
    hunter = ThreatHunter()
    planner = AttackPlanner()
    generator = AttackGenerator()
    client = SandboxClient()
    analyzer = FailureAnalyzer()

    print_kb_section(kb)

    if family_id:
        family = kb.get_family(family_id)
        if not family:
            print(f"\nERROR: Family {family_id} not found in KB")
            sys.exit(1)
        families = [family]
    else:
        families = kb.get_simulatable_families()[:max_families]

    sep(f"CONTINUOUS RUN — {len(families)} KB families")
    summary = []

    for i, family in enumerate(families, 1):
        print(f"\n{'#' * 72}")
        print(f"# CAMPAIGN {i}/{len(families)}: {family.get('attack_id')} — {family.get('name')}")
        print(f"{'#' * 72}")

        if not is_simulatable(family):
            print(f"  SKIPPED (not simulatable: {family.get('simulation_type')})")
            continue

        result = run_family_campaign(
            family, hunter, planner, generator, client, analyzer
        )
        summary.append(result)

    sep("SECTION 4: RUN SUMMARY")
    for s in summary:
        successes = s["outcomes"].count("success")
        print(
            f"  {s['family_id']:10s}  steps={s['steps_executed']}  "
            f"final={s['final_decision']}  successes={successes}/{len(s['outcomes'])}"
        )

    stats = kb.kb_stats()
    print(f"\n  KB coverage this run: {len(summary)}/{stats['simulatable_families']} simulatable families")
    print(f"  Total KB: {stats['total_families']} families | "
          f"{stats['total_signals']} signals | {stats['total_stages']} stages")
    print("\n  ✅ Dynamic KB → Red Team → Sandbox run complete")


def main():
    parser = argparse.ArgumentParser(description="Dynamic KB Red Team Sandbox test")
    parser.add_argument("--families", type=int, default=5, help="Number of simulatable families to run")
    parser.add_argument("--family", type=str, default=None, help="Run a single family by attack_id (e.g. AUT-001)")
    args = parser.parse_args()
    run_continuous(max_families=args.families, family_id=args.family)


if __name__ == "__main__":
    main()
