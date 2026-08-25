"""
Continuous Red Team campaign runner (KB -> Planner -> Generator -> Sandbox).

Used by test scripts and loop_runner. No LLM/Bedrock required by default.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional

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
from .schemas import Hypothesis


def _linear_retry_limit() -> int:
    try:
        return max(0, int(os.environ.get("RED_TEAM_LINEAR_RETRIES", "2")))
    except ValueError:
        return 2


def _hard_negatives_enabled() -> bool:
    return os.environ.get("RED_TEAM_HARD_NEGATIVES", "false").lower() in ("1", "true", "yes")


def _hard_negative_count() -> int:
    try:
        return max(1, int(os.environ.get("RED_TEAM_HARD_NEGATIVE_COUNT", "3")))
    except ValueError:
        return 3


def _tested_family_ids(memory: MemoryAgent) -> set:
    return {
        fid
        for fid in (
            m.applicable_conditions.get("primary_family")
            for m in memory.memories
        )
        if fid
    }


def select_families(
    kb: OfflineKnowledge,
    *,
    max_families: int = 5,
    family_id: Optional[str] = None,
    memory: Optional[MemoryAgent] = None,
) -> List[Dict[str, Any]]:
    if family_id:
        family = kb.get_family(family_id)
        return [family] if family else []

    memory = memory or MemoryAgent()
    strategy = StrategyLayer(memory)
    tested = _tested_family_ids(memory)
    ranked = strategy.prioritized_candidates(tested)
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


def run_hard_negatives(
    count: Optional[int] = None,
    buffer: Optional[Any] = None,
) -> Dict[str, Any]:
    """Generate hard-negative evidence rows (suspicious-but-legitimate)."""
    from backend.blue_team.hard_negatives import HardNegativeGenerator
    from backend.blue_team.evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH

    n = count if count is not None else _hard_negative_count()
    buffer_path = os.environ.get(
        "HARD_NEGATIVE_BUFFER_PATH",
        os.environ.get("EVIDENCE_BUFFER_PATH", DEFAULT_BUFFER_PATH),
    )
    evidence_buffer = buffer or EvidenceBuffer(buffer_path)
    generator = HardNegativeGenerator(buffer=evidence_buffer)
    records = generator.generate(count=n)
    return {
        "hard_negatives_generated": len(records),
        "hard_negative_ids": [r.evidence_id for r in records],
    }


def _execute_payload_with_retries(
    payload,
    *,
    client: SandboxClient,
    analyzer: FailureAnalyzer,
    plan,
    mutator: LinearMutator,
    hypothesis: Hypothesis,
    memory: Optional[MemoryAgent] = None,
    collector: Optional[Any] = None,
    print_sections: bool = True,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    run_id: Optional[str] = None,
    family_id: Optional[str] = None,
    family_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Execute payload + linear retries; store memory and optional evidence."""
    results: List[Dict[str, Any]] = []
    linear_limit = _linear_retry_limit()
    payloads_to_run = [payload]

    for current in payloads_to_run:
        response = client.execute_payload(current.model_dump())
        if print_sections:
            _print_sandbox_step(current.step, current.action_type, response, current)

        analysis = analyzer.analyze(response, current, plan)
        if memory:
            memory.store_analysis(analysis, hypothesis, {"payload_index": current.step})

        event_record = None
        if collector:
            event_record = collector.collect(
                response, current, plan, hypothesis, analysis, client.get_sandbox()
            )
            if event_record and on_event:
                on_event({
                    "loop_run_id": run_id,
                    "family_id": family_id,
                    "family_name": family_name,
                    "step": event_record.step,
                    "sandbox_decision": event_record.sandbox_decision,
                    "evasion_outcome": event_record.evasion_outcome,
                    "ml_score": event_record.ml_score,
                    "amount": event_record.amount,
                })

        results.append({
            "step": current.step,
            "action_type": current.action_type,
            "decision": response.get("decision"),
            "triggers": response.get("control_triggers"),
            "outcome": analysis.outcome,
            "variation": current.variation_label,
            "linear": "linear" in (current.variation_label or ""),
            "control_gap": bool(analysis.control_gap_detected),
            "collector_record": event_record is not None,
        })

        if (
            current.action_type == "initiate_payment"
            and analysis.outcome == "failure"
            and linear_limit > 0
            and not (current.variation_label or "").startswith("linear_")
        ):
            for attempt in range(linear_limit):
                mutated = mutator.mutate(current, analysis, attempt=attempt)
                response = client.execute_payload(mutated.model_dump())
                if print_sections:
                    _print_sandbox_step(
                        mutated.step, mutated.action_type, response, mutated, retry=attempt + 1
                    )
                analysis = analyzer.analyze(response, mutated, plan)
                if memory:
                    memory.store_analysis(analysis, hypothesis, {"linear_retry": attempt + 1})

                event_record = None
                if collector:
                    event_record = collector.collect(
                        response, mutated, plan, hypothesis, analysis, client.get_sandbox()
                    )
                    if event_record and on_event:
                        on_event({
                            "loop_run_id": run_id,
                            "family_id": family_id,
                            "family_name": family_name,
                            "step": event_record.step,
                            "sandbox_decision": event_record.sandbox_decision,
                            "evasion_outcome": event_record.evasion_outcome,
                            "ml_score": event_record.ml_score,
                            "amount": event_record.amount,
                        })

                results.append({
                    "step": mutated.step,
                    "action_type": mutated.action_type,
                    "decision": response.get("decision"),
                    "triggers": response.get("control_triggers"),
                    "outcome": analysis.outcome,
                    "variation": mutated.variation_label,
                    "linear": True,
                    "control_gap": bool(analysis.control_gap_detected),
                    "collector_record": event_record is not None,
                })
                if analysis.outcome == "success":
                    break

    return results


def run_family_campaign(
    family: dict,
    hunter: ThreatHunter,
    planner: AttackPlanner,
    generator: AttackGenerator,
    client: SandboxClient,
    analyzer: FailureAnalyzer,
    mutator: LinearMutator,
    *,
    memory: Optional[MemoryAgent] = None,
    collector: Optional[Any] = None,
    print_sections: bool = True,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    run_id: Optional[str] = None,
) -> dict:
    """Run one KB family (optionally all tree branches) through Red Team -> Sandbox."""
    strategy = os.environ.get("RED_TEAM_JAILBREAK_STRATEGY", "kb")
    hypothesis = hunter.hypothesis_from_family(family)
    hypothesis.jailbreak_strategy = strategy

    if strategy == "tree":
        plans = planner.plan_branches(hypothesis)
    else:
        plans = [planner.plan(hypothesis)]

    if print_sections:
        _print_red_team_header(family, hypothesis, plans)

    all_results: List[Dict[str, Any]] = []
    gap_count = 0
    total_generated = 0

    for branch_idx, plan in enumerate(plans):
        if print_sections and len(plans) > 1:
            label = plan.branch_label or f"branch_{branch_idx + 1}"
            print(f"\n  Tree branch {branch_idx + 1}/{len(plans)}: {label}")

        sequence = generator.generate_sequence(plan)
        total_generated += sequence.total_payloads
        if print_sections and len(plans) == 1:
            _print_sequence(sequence)

        if print_sections:
            _sep(f"SANDBOX OUTPUT - {family.get('attack_id')}", char="-")

        branch_results: List[Dict[str, Any]] = []
        for payload in sequence.payloads:
            batch = _execute_payload_with_retries(
                payload,
                client=client,
                analyzer=analyzer,
                plan=plan,
                mutator=mutator,
                hypothesis=hypothesis,
                memory=memory,
                collector=collector,
                print_sections=print_sections,
                on_event=on_event,
                run_id=run_id,
                family_id=family.get("attack_id"),
                family_name=family.get("name", "")[:80],
            )
            branch_results.extend(batch)
            gap_count += sum(1 for r in batch if r.get("control_gap"))

        all_results.extend(branch_results)

        if branch_results and analyzer:
            last_payload_analysis = branch_results[-1]
            if print_sections:
                print(f"  Branch {branch_idx + 1} final: {last_payload_analysis.get('decision')}")

    if print_sections and all_results:
        last = all_results[-1]
        print(f"\n  Final decision={last.get('decision')}  gaps_this_family={gap_count}")

    return {
        "family_id": family.get("attack_id"),
        "strategy": strategy,
        "branches": len(plans),
        "steps_executed": len(all_results),
        "payloads_generated": total_generated,
        "final_decision": all_results[-1]["decision"] if all_results else None,
        "outcomes": [r["outcome"] for r in all_results],
        "linear_retries_used": sum(1 for r in all_results if r.get("linear")),
        "control_gaps": gap_count,
    }


def run_red_team_for_loop(
    *,
    families: int = 5,
    collector: Optional[Any] = None,
    run_id: Optional[str] = None,
    on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    print_sections: bool = False,
) -> Dict[str, Any]:
    """Red team step for LoopRunner with memory, gaps, and optional hard negatives."""
    kb = OfflineKnowledge()
    memory = MemoryAgent()
    hunter = ThreatHunter()
    planner = AttackPlanner()
    generator = AttackGenerator()
    client = SandboxClient()
    analyzer = FailureAnalyzer()
    mutator = LinearMutator()

    selected = select_families(kb, max_families=families, memory=memory)
    campaign_events: List[Dict[str, Any]] = []

    def _capture_event(event: Dict[str, Any]) -> None:
        campaign_events.append(event)
        if on_event:
            on_event(event)

    summaries: List[dict] = []
    for family in selected:
        summaries.append(run_family_campaign(
            family, hunter, planner, generator, client, analyzer, mutator,
            memory=memory,
            collector=collector,
            print_sections=print_sections,
            on_event=_capture_event,
            run_id=run_id,
        ))

    gap_report = analyzer.control_gap_lab.export_report()
    hn_report: Dict[str, Any] = {}
    if _hard_negatives_enabled():
        hn_report = run_hard_negatives()

    return {
        "summaries": summaries,
        "campaign_events": campaign_events,
        "memory_entries": len(memory.memories),
        "control_gap_report": gap_report,
        "hard_negatives": hn_report,
    }


def run_continuous(
    max_families: int = 5,
    family_id: Optional[str] = None,
    *,
    print_sections: bool = True,
) -> List[dict]:
    kb = OfflineKnowledge()
    memory = MemoryAgent()
    hunter = ThreatHunter()
    planner = AttackPlanner()
    generator = AttackGenerator()
    client = SandboxClient()
    analyzer = FailureAnalyzer()
    mutator = LinearMutator()

    if print_sections:
        _print_kb_section(kb, memory)

    families = select_families(kb, max_families=max_families, family_id=family_id, memory=memory)
    if not families:
        print("ERROR: No simulatable families found")
        return []

    if print_sections:
        _sep(f"CONTINUOUS RUN - {len(families)} families (CVSS + memory)")
        print(
            f"  strategy={os.environ.get('RED_TEAM_JAILBREAK_STRATEGY', 'kb')}  "
            f"attack_engine={os.environ.get('RED_TEAM_USE_ATTACK_ENGINE', 'true')}  "
            f"linear_retries={_linear_retry_limit()}  "
            f"hard_negatives={_hard_negatives_enabled()}"
        )

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
            memory=memory,
            print_sections=print_sections,
        ))

    gap_report = analyzer.control_gap_lab.export_report()
    hn_report: Dict[str, Any] = {}
    if _hard_negatives_enabled():
        hn_report = run_hard_negatives()
        if print_sections:
            print(f"\n  Hard negatives generated: {hn_report.get('hard_negatives_generated', 0)}")

    if print_sections:
        _sep("RUN SUMMARY")
        total_payloads = 0
        for s in summary:
            total_payloads += s["steps_executed"]
            successes = s["outcomes"].count("success")
            print(
                f"  {s['family_id']:10s}  strategy={s.get('strategy', 'kb'):10s}  "
                f"branches={s.get('branches', 1)}  "
                f"executed={s['steps_executed']}  linear+={s.get('linear_retries_used', 0)}  "
                f"gaps={s.get('control_gaps', 0)}  "
                f"successes={successes}/{len(s['outcomes'])}"
            )
        stats = kb.kb_stats()
        print(f"\n  Total sandbox executions: {total_payloads}")
        print(f"  Memory entries stored: {len(memory.memories)}")
        print(
            f"  Control gaps: {gap_report.get('control_gaps', 0)} "
            f"(findings={gap_report.get('total_findings', 0)})"
        )
        print(f"  KB: {stats['total_families']} families | {stats['simulatable_families']} simulatable")
        print("\n  OK Dynamic KB -> Red Team -> Sandbox continuous run complete")
        print("  (Bedrock/LLM not required; set RED_TEAM_USE_LLM=true + LLM_PROVIDER=bedrock later)")

    return summary


def _sep(title: str, char: str = "=", width: int = 72) -> None:
    print(f"\n{char * width}\n{title}\n{char * width}")


def _print_kb_section(kb: OfflineKnowledge, memory: MemoryAgent) -> None:
    _sep("KNOWLEDGE BASE (canonical -> KnowledgeLoader)")
    stats = kb.kb_stats()
    print(f"  families={stats['total_families']}  signals={stats['total_signals']}  stages={stats['total_stages']}")
    print(f"  simulatable={stats['simulatable_families']}")
    top = StrategyLayer(memory).prioritized_candidates(_tested_family_ids(memory))[:5]
    if top:
        print("  CVSS top 5:", ", ".join(f"{c.family_id}({c.cvss.composite})" for c in top))


def _print_red_team_header(family, hypothesis, plans) -> None:
    _sep(f"RED TEAM - {family.get('attack_id')}")
    print(f"  pattern={classify_family(family)}  strategy={plans[0].jailbreak_strategy}")
    if len(plans) > 1:
        print(f"  tree branches={len(plans)}")


def _print_sequence(sequence) -> None:
    print(f"  plan payloads={sequence.total_payloads}")
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
