#!/usr/bin/env python3
"""
Multi-surface Red -> Sandbox -> Blue loop with adaptive evasion search.

Runs the closed loop the way the three pillars are meant to compose:

  1. Red plans a campaign per KB family, on the surface that adjudicates it
  2. The evasion search probes each surface's mutation space and bisects for the
     boundary — the strongest attack that still gets through
  3. Every probe is adjudicated by the sandbox and collected as evidence
  4. Composite chains cross surfaces on shared state and measure what the
     upstream attack bought the attacker
  5. Blue's training mix is assembled, showing per-surface coverage

Prints an ASR table by surface. Nothing here labels its own success: every
verdict comes from the sandbox.

Usage:
  python scripts/run_multi_surface_loop.py [--families N] [--no-composites]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from backend.blue_team.collector import EvidenceCollector  # noqa: E402
from backend.blue_team.evidence_buffer import EvidenceBuffer  # noqa: E402
from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader  # noqa: E402
from backend.red_team.composite_campaign import COMPOSITE_CHAINS, CompositeRunner  # noqa: E402
from backend.red_team.evasion_search import EvasionSearch  # noqa: E402
from backend.red_team.kb_template_planner import build_plan_from_template  # noqa: E402
from backend.sandbox import PaymentSandbox  # noqa: E402
from backend.taxonomy import SURFACE_ENTRY_ACTION  # noqa: E402

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
        entry = SURFACE_ENTRY_ACTION[surface]
        step = next((s for s in plan.steps if s.action_type == entry), None)
        if step is None:
            continue

        base = dict(step.payload_template or {})
        base["customer_id"] = f"C_{family_id}"
        base["device_id"] = f"D_{family_id}"
        probe_index = {"n": 0}

        def execute(payload, family_id=family_id, entry=entry, plan=plan, probe_index=probe_index):
            # Fresh sandbox per probe: probes are independent experiments, so state
            # from one must not leak into the next.
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
    """Composite chains are reported, not collected: their value is the
    contextual-vs-isolated comparison, which is a campaign-level measurement
    rather than a per-row training example."""
    runner = CompositeRunner(lambda: PaymentSandbox())
    return [runner.run_best(chain).summary() for chain in COMPOSITE_CHAINS]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--families", type=int, default=0, help="limit families (0 = all)")
    parser.add_argument("--no-composites", action="store_true")
    parser.add_argument("--buffer", default="", help="evidence buffer path (default: temp)")
    args = parser.parse_args()

    os.environ.setdefault("FRAUDSHIELD_ENABLED", "false")

    buffer_path = args.buffer or os.path.join(tempfile.mkdtemp(), "evidence.jsonl")
    buffer = EvidenceBuffer(buffer_path)
    collector = EvidenceCollector(buffer=buffer)
    kb = CanonicalKnowledgeLoader()

    surface_families = [f["attack_id"] for f in kb.families if f.get("surface") not in (None, "payment")]
    if args.families:
        surface_families = surface_families[: args.families]

    print("=" * 78)
    print("PHASE 1: Red Team evasion search across control surfaces")
    print("=" * 78)
    search_out = run_surface_search(kb, collector, surface_families)

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

    if not args.no_composites:
        print()
        print("=" * 78)
        print("PHASE 2: Composite campaigns across surfaces (shared state)")
        print("=" * 78)
        print(f"{'chain':32s} {'int':5s} {'cash-out':10s} {'isolated':10s} {'gain':5s} upstream compromise")
        print("-" * 78)
        for row in run_composites():
            gain = row["attacker_gain"]
            print(
                f"{row['chain']:32s} {row['intensity']:<5.2f} "
                f"{row['terminal_decision']:10s} {str(row['isolated_decision']):10s} "
                f"{gain:+d}    {','.join(row['compromises']) or '-'}"
            )

    print()
    print("=" * 78)
    print("PHASE 3: Blue Team evidence and training mix")
    print("=" * 78)
    stats = buffer.stats()
    print(f"adjudicated rows : {stats['adjudicated_records']}")
    print(f"bypassed/blocked : {stats['bypassed']} / {stats['blocked']}")
    print(f"families         : {len(stats['families'])}")
    print(f"rows by surface  : {stats['surfaces']}")

    try:
        from backend.blue_team.trainer import HardeningTrainer
        from backend.blue_team.training_mix import build_hardening_dataset

        baseline = HardeningTrainer().load_baseline_sample(n_legit=4000, n_fraud=4000)
        _, _, manifest = build_hardening_dataset(baseline, buffer.read_all())
        print()
        print(f"split            : {manifest['split_method']}")
        print(f"train sources    : {manifest['train_sources']}")
        print(f"val sources      : {manifest['val_sources']}")
        print(
            f"adv campaigns    : {manifest['adv_campaigns_train']} train / "
            f"{manifest['adv_campaigns_val']} val (disjoint={manifest['campaign_disjoint']})"
        )
    except FileNotFoundError as exc:
        print(f"\n[skip] training mix needs the baseline dataset: {exc}")

    print()
    print(f"evidence buffer: {buffer_path}")


if __name__ == "__main__":
    main()
