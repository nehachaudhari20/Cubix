"""
Multi-surface evasion search + cross-surface composite campaigns.

Shared by LoopRunner (full product loop) and scripts/run_multi_surface_loop.py.
Every probe is sandbox-adjudicated and collected into the caller's evidence buffer.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader
from backend.red_team.composite_campaign import COMPOSITE_CHAINS, CompositeRunner
from backend.red_team.evasion_search import EvasionSearch
from backend.red_team.kb_template_planner import build_plan_from_template
from backend.sandbox import PaymentSandbox
from backend.taxonomy import SURFACE_ENTRY_ACTION

SETUP_ACTIONS = ("register_customer", "register_device", "link_beneficiary")


def _collect(collector, sandbox, observation, action_type, payload, family_id, campaign_id, step):
    response = observation.to_legacy_response()
    response.update(
        {
            "decision": observation.decision,
            "control_triggers": observation.control_triggers,
            "state_snapshot": observation.state_snapshot,
            "surface": observation.surface,
        }
    )
    collector.collect(
        response,
        {
            "action_type": action_type,
            "action_payload": payload,
            "campaign_id": campaign_id,
            "step": step,
        },
        {"primary_family": family_id},
        None,
        None,
        sandbox,
    )


def run_surface_search(kb, collector, families: List[str]) -> Dict[str, Any]:
    """Evasion search per family, collecting every probe as evidence."""
    search = EvasionSearch()
    per_surface: Dict[str, Dict[str, int]] = defaultdict(lambda: {"probes": 0, "evaded": 0})
    rows: List[Dict[str, Any]] = []

    for family_id in families:
        family = kb.get_family(family_id)
        surface = family.get("surface")
        if not surface or surface == "payment":
            continue

        plan = build_plan_from_template(
            family, kb.get_family_stages(family_id) or [], kb.signals[:20]
        )
        entry = SURFACE_ENTRY_ACTION.get(surface)
        if not entry:
            continue
        step = next((s for s in plan.steps if s.action_type == entry), None)
        if step is None:
            continue

        base = dict(step.payload_template or {})
        base["customer_id"] = f"C_{family_id}"
        base["device_id"] = f"D_{family_id}"
        probe_index = {"n": 0}

        def execute(payload, family_id=family_id, entry=entry, plan=plan, probe_index=probe_index):
            # Fresh sandbox per probe: probes are independent experiments.
            sandbox = PaymentSandbox()
            for setup in plan.steps:
                if setup.action_type not in SETUP_ACTIONS:
                    continue
                setup_payload = dict(setup.payload_template or {})
                setup_payload["customer_id"] = f"C_{family_id}"
                setup_payload["device_id"] = f"D_{family_id}"
                if setup.action_type == "link_beneficiary":
                    setup_payload["beneficiary_id"] = f"B_{family_id}"
                sandbox.execute(setup.action_type, setup_payload)

            observation = sandbox.execute(entry, payload)
            probe_index["n"] += 1
            _collect(
                collector,
                sandbox,
                observation,
                entry,
                payload,
                family_id,
                f"search_{family_id}",
                probe_index["n"],
            )
            return observation

        result = search.search(surface, base, execute, family_id=family_id)
        per_surface[surface]["probes"] += len(result.probes)
        per_surface[surface]["evaded"] += result.evaded_count
        rows.append(result.summary())

    return {"per_surface": dict(per_surface), "rows": rows}


def run_composites() -> List[Dict[str, Any]]:
    """Composite chains: contextual-vs-isolated comparison at campaign level."""
    runner = CompositeRunner(lambda: PaymentSandbox())
    return [runner.run_best(chain).summary() for chain in COMPOSITE_CHAINS]


def list_surface_families(kb: Optional[CanonicalKnowledgeLoader] = None, limit: int = 0) -> List[str]:
    kb = kb or CanonicalKnowledgeLoader()
    families = [
        f["attack_id"]
        for f in kb.families
        if f.get("surface") not in (None, "payment") and f.get("attack_id")
    ]
    if limit:
        families = families[:limit]
    return families


def run_multi_surface_phase(
    collector,
    *,
    family_limit: int = 0,
    include_composites: bool = True,
    print_sections: bool = True,
) -> Dict[str, Any]:
    """
    Run evasion search (+ optional composites) into an existing EvidenceCollector.

    Appends to the collector's buffer; does not clear it.
    """
    kb = CanonicalKnowledgeLoader()
    surface_families = list_surface_families(kb, limit=family_limit)

    if print_sections:
        print("=" * 78)
        print("MULTI-SURFACE: Red Team evasion search across control surfaces")
        print("=" * 78)
        print(f"  Non-payment families: {len(surface_families)}")

    search_out = run_surface_search(kb, collector, surface_families)

    if print_sections:
        print(f"{'family':10s} {'surface':13s} {'probes':7s} {'evaded':7s} {'ASR':8s} boundary")
        print("-" * 78)
        for row in search_out["rows"]:
            boundary = row["boundary_intensity"]
            boundary_text = f"{boundary:.3f}" if boundary is not None else "closed"
            print(
                f"{row['family_id']:10s} {row['surface']:13s} {row['probes']:<7d} "
                f"{row['evaded']:<7d} {row['asr']:<8.1%} {boundary_text}"
            )

        print()
        print(f"{'surface':14s} {'probes':8s} {'evaded':8s} ASR")
        print("-" * 78)
        total_p = total_e = 0
        for surface, stats in sorted(search_out["per_surface"].items()):
            asr = stats["evaded"] / stats["probes"] if stats["probes"] else 0.0
            total_p += stats["probes"]
            total_e += stats["evaded"]
            print(f"{surface:14s} {stats['probes']:<8d} {stats['evaded']:<8d} {asr:.1%}")
        overall = total_e / total_p if total_p else 0.0
        print(f"{'TOTAL':14s} {total_p:<8d} {total_e:<8d} {overall:.1%}")

    composite_rows: List[Dict[str, Any]] = []
    if include_composites:
        if print_sections:
            print()
            print("=" * 78)
            print("MULTI-SURFACE: Composite campaigns across surfaces (shared state)")
            print("=" * 78)
            print(
                f"{'chain':32s} {'int':5s} {'cash-out':10s} {'isolated':10s} "
                f"{'gain':5s} upstream compromise"
            )
            print("-" * 78)
        composite_rows = run_composites()
        if print_sections:
            for row in composite_rows:
                gain = row["attacker_gain"]
                print(
                    f"{row['chain']:32s} {row['intensity']:<5.2f} "
                    f"{row['terminal_decision']:10s} {str(row['isolated_decision']):10s} "
                    f"{gain:+d}    {','.join(row['compromises']) or '-'}"
                )

    total_probes = sum(s["probes"] for s in search_out["per_surface"].values())
    total_evaded = sum(s["evaded"] for s in search_out["per_surface"].values())
    return {
        "families_searched": len(surface_families),
        "search": search_out,
        "composites": composite_rows,
        "total_probes": total_probes,
        "total_evaded": total_evaded,
        "overall_asr": (total_evaded / total_probes) if total_probes else 0.0,
    }
