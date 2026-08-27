#!/usr/bin/env python3
"""
Replace TPL-AGENTIC-NONEXEC with real simulation templates and flip the affected
KB families to sandbox_executable.

Before this script, 21 of 57 families pointed at TPL-AGENTIC-NONEXEC — a template
with an empty `supported_action_types` list — so the only way to "execute" them was
to force a payment leg and score an agentic attack as a transaction.

Each family is assigned:
  - the simulation template for the surface that actually adjudicates it
  - the granular technique(s) from backend/taxonomy/techniques.py
  - sandbox_executable = True

Idempotent: re-running produces the same KB. Families with no technique mapping are
left non-executable and reported, so the gap stays visible rather than silently
assumed away.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = ROOT / "data" / "knowledge" / "canonical"

from backend.taxonomy import SURFACE_ENTRY_ACTION, techniques_for_family  # noqa: E402

# Surface -> (template_id, template name, campaign pattern, required entities)
SURFACE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "agent": {
        "template_id": "TPL-AGENT",
        "name": "Agentic commerce manipulation journey",
        "campaign_pattern": "agentic",
        "required_entities": ["customer", "agent"],
        "required_state_keys": ["customer_id", "agent_id"],
        "parameter_ids": ["PAR-AMOUNT", "PAR-TIMING"],
        "state_requirement_id": "SRQ-AGENT",
        "mutation_dimensions": ["agent_goal", "tool_scope", "timing"],
    },
    "auth_se": {
        "template_id": "TPL-AUTH-SE",
        "name": "Authentication social-engineering journey",
        "campaign_pattern": "auth_se",
        "required_entities": ["customer", "device"],
        "required_state_keys": ["customer_id"],
        "parameter_ids": ["PAR-TIMING", "PAR-SESSION-DURATION"],
        "state_requirement_id": "SRQ-AUTH-SE",
        "mutation_dimensions": ["channel", "pressure", "timing"],
    },
    "kyc": {
        "template_id": "TPL-KYC-GENAI",
        "name": "GenAI identity-evidence submission journey",
        "campaign_pattern": "kyc_genai",
        "required_entities": ["customer"],
        "required_state_keys": ["customer_id"],
        "parameter_ids": ["PAR-TRUST-SCORE", "PAR-ACCOUNT-AGE"],
        "state_requirement_id": "SRQ-KYC-GENAI",
        "mutation_dimensions": ["evidence_type", "trust_score"],
    },
    "open_banking": {
        "template_id": "TPL-OB-CONSENT",
        "name": "Open-banking consent abuse journey",
        "campaign_pattern": "open_banking",
        "required_entities": ["customer", "tpp", "consent"],
        "required_state_keys": ["customer_id", "tpp_id"],
        "parameter_ids": ["PAR-TIMING"],
        "state_requirement_id": "SRQ-OB-CONSENT",
        "mutation_dimensions": ["scope_breadth", "token_state"],
    },
    "device": {
        "template_id": "TPL-SESSION",
        "name": "Device / session integrity attack journey",
        "campaign_pattern": "session",
        "required_entities": ["customer", "device"],
        "required_state_keys": ["customer_id", "device_id"],
        "parameter_ids": ["PAR-DEVICE-AGE", "PAR-SESSION-DURATION"],
        "state_requirement_id": "SRQ-SESSION",
        "mutation_dimensions": ["interaction_timing", "behavioural_variance"],
    },
    "network": {
        "template_id": "TPL-NETWORK",
        "name": "Cross-account network orchestration journey",
        "campaign_pattern": "network",
        "required_entities": ["customer", "beneficiary", "payment"],
        "required_state_keys": ["customer_id", "member_customer_ids"],
        "parameter_ids": ["PAR-AMOUNT", "PAR-VELOCITY", "PAR-BENEFICIARY-NOVELTY"],
        "state_requirement_id": "SRQ-NETWORK",
        "mutation_dimensions": ["ring_size", "fan_in", "timing"],
    },
}

CONSTRAINTS = [
    "Do not independently randomize amount, device, merchant, beneficiary, geo, and velocity.",
    "Sample legitimate baseline first, then mutate attacker-controllable parameters.",
]

# Setup steps each surface needs before its adjudicated action can run.
SURFACE_SETUP: Dict[str, List[str]] = {
    "agent": ["register_customer"],
    "auth_se": ["register_customer", "register_device"],
    "kyc": ["register_customer"],
    "open_banking": ["register_customer"],
    "device": ["register_customer", "register_device"],
    "network": ["register_customer", "register_device", "link_beneficiary"],
}

# Surfaces whose attack chain ends in a cash-out leg.
SURFACE_CASHOUT = {"network"}


def build_template(surface: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    entry = SURFACE_ENTRY_ACTION[surface]
    actions = list(SURFACE_SETUP[surface]) + [entry]
    if surface in SURFACE_CASHOUT:
        actions.append("initiate_payment")
    return {
        "template_id": spec["template_id"],
        "name": spec["name"],
        "campaign_pattern": spec["campaign_pattern"],
        "required_entities": spec["required_entities"],
        "supported_action_types": actions,
        "required_state_keys": spec["required_state_keys"],
        "parameter_ids": spec["parameter_ids"],
        "state_requirement_id": spec["state_requirement_id"],
        "parameter_schema_ref": None,
        "mutation_dimensions": spec["mutation_dimensions"],
        "constraints": CONSTRAINTS,
        "surface": surface,
        "origin": "surface_enabled",
        "evidence": [],
    }


def build_state_requirement(surface: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "requirement_id": spec["state_requirement_id"],
        "name": f"{spec['name']} required state",
        "required_entities": spec["required_entities"],
        "required_state": {key: True for key in spec["required_state_keys"]},
        "notes": (
            "Derived from the sandbox surface handler in "
            "backend/sandbox/surface_adjudicator.py. Not PDF-invented thresholds."
        ),
        "origin": "implementation_derived",
    }


def migrate_vectors(
    vectors: List[Dict[str, Any]],
    family_surface: Dict[str, str],
    family_template: Dict[str, str],
) -> Dict[str, int]:
    """
    Point the vectors of surface-enabled families at their new template and give
    them real ordered_actions.

    132 vectors carried a single `specify_only` step meaning "the sandbox cannot
    execute this". They now carry the surface's actual action sequence, so a vector
    is an executable instance rather than a specification.
    """
    stats = {"migrated": 0, "skipped": 0, "payment_retargeted": 0}
    for vector in vectors:
        family_id = vector.get("family_id") or ""
        surface = family_surface.get(family_id)
        if not surface:
            stats["skipped"] += 1
            continue

        if surface == "payment":
            # Payment-surface families keep the 15-engine chain; their vectors only
            # need to stop pointing at the removed placeholder template.
            if vector.get("simulation_template_id") == "TPL-AGENTIC-NONEXEC":
                target = family_template.get(family_id, "TPL-PAYMENT-PROBE")
                vector["simulation_template_id"] = target
                vector["simulation_template_ref"] = target
                vector["state_requirement_id"] = "SRQ-PAYMENT-PROBE"
                vector["sandbox_executable"] = True
                vector["surface"] = "payment"
                vector["ordered_actions"] = [
                    {"action_id": "step-01", "action_type": "register_customer",
                     "parameters": {"parameter_refs": ["PAR-TRUST-SCORE"]}},
                    {"action_id": "step-02", "action_type": "register_device",
                     "parameters": {"parameter_refs": ["PAR-DEVICE-AGE"]}},
                    {"action_id": "step-03", "action_type": "initiate_payment",
                     "parameters": {"parameter_refs": ["PAR-AMOUNT", "PAR-RAIL", "PAR-TIMING"]}},
                ]
                stats["payment_retargeted"] += 1
            else:
                stats["skipped"] += 1
            continue

        spec = SURFACE_TEMPLATES[surface]

        vector["simulation_template_id"] = spec["template_id"]
        vector["simulation_template_ref"] = spec["template_id"]
        vector["state_requirement_id"] = spec["state_requirement_id"]
        vector["sandbox_executable"] = True
        vector["surface"] = surface
        vector["mutation_dimensions"] = sorted(
            set(vector.get("mutation_dimensions") or []) | set(spec["mutation_dimensions"])
        )

        actions = list(SURFACE_SETUP[surface]) + [SURFACE_ENTRY_ACTION[surface]]
        if surface in SURFACE_CASHOUT:
            actions.append("initiate_payment")
        param_refs = spec["parameter_ids"]
        vector["ordered_actions"] = [
            {
                "action_id": f"step-{index:02d}",
                "action_type": action,
                "parameters": {"parameter_refs": param_refs},
            }
            for index, action in enumerate(actions, start=1)
        ]
        vector["success_conditions"] = [
            f"{SURFACE_ENTRY_ACTION[surface]} returns ALLOW or CHALLENGE",
            "expected controls for the family are not all triggered",
        ]
        stats["migrated"] += 1
    return stats


def migrate_relationships(
    relationships: List[Dict[str, Any]],
    vector_template: Dict[str, str],
) -> int:
    """Repoint `uses_template` edges away from the removed placeholder template."""
    migrated = 0
    for rel in relationships:
        if rel.get("relationship_type") != "uses_template":
            continue
        if rel.get("to_ref") != "TPL-AGENTIC-NONEXEC":
            continue
        new_template = vector_template.get(rel.get("from_ref") or "")
        if not new_template:
            continue
        rel["to_ref"] = new_template
        migrated += 1
    return migrated


def main() -> None:
    tpl_path = BASE / "simulation" / "simulation_templates.json"
    fam_path = BASE / "attacks" / "attack_families.json"
    vec_path = BASE / "attacks" / "attack_vectors.json"
    srq_path = BASE / "simulation" / "state_requirements.json"
    rel_path = BASE / "attacks" / "attack_relationships.json"

    tpl_payload = json.loads(tpl_path.read_text(encoding="utf-8"))
    fam_payload = json.loads(fam_path.read_text(encoding="utf-8"))
    vec_payload = json.loads(vec_path.read_text(encoding="utf-8"))
    srq_payload = json.loads(srq_path.read_text(encoding="utf-8"))
    rel_payload = json.loads(rel_path.read_text(encoding="utf-8"))

    # --- templates: keep payment ones, drop the placeholder, add surface ones ---
    templates = [
        t for t in tpl_payload["simulation_templates"]
        if t["template_id"] != "TPL-AGENTIC-NONEXEC"
        and t["template_id"] not in {s["template_id"] for s in SURFACE_TEMPLATES.values()}
    ]
    for surface, spec in SURFACE_TEMPLATES.items():
        templates.append(build_template(surface, spec))

    tpl_payload["simulation_templates"] = templates
    tpl_payload["built_at"] = datetime.now(timezone.utc).isoformat()
    tpl_path.write_text(json.dumps(tpl_payload, indent=2), encoding="utf-8")

    # --- state requirements: drop the placeholder, add one per surface ----------
    surface_srq_ids = {s["state_requirement_id"] for s in SURFACE_TEMPLATES.values()}
    requirements = [
        r for r in srq_payload["state_requirements"]
        if r["requirement_id"] != "SRQ-AGENTIC-NONEXEC"
        and r["requirement_id"] not in surface_srq_ids
    ]
    for surface, spec in SURFACE_TEMPLATES.items():
        requirements.append(build_state_requirement(surface, spec))
    srq_payload["state_requirements"] = requirements
    srq_payload["built_at"] = datetime.now(timezone.utc).isoformat()
    srq_path.write_text(json.dumps(srq_payload, indent=2), encoding="utf-8")

    # --- families: assign surface template + techniques, flip executable -------
    enabled: List[str] = []
    still_blocked: List[str] = []
    family_surface: Dict[str, str] = {}

    for family in fam_payload["attack_families"]:
        attack_id = family.get("attack_id")
        techniques = techniques_for_family(attack_id)
        if not techniques:
            if family.get("simulation_template_id") == "TPL-AGENTIC-NONEXEC":
                still_blocked.append(attack_id)
            continue

        surface = techniques[0].surface
        if surface == "payment":
            # Payment-surface families already have a working 15-engine chain;
            # they only need a template with real supported_action_types.
            family["simulation_template_id"] = (
                family.get("simulation_template_id")
                if family.get("simulation_template_id") != "TPL-AGENTIC-NONEXEC"
                else "TPL-PAYMENT-PROBE"
            )
            family["surface"] = "payment"
            family["technique_ids"] = [t.action_type for t in techniques]
            family["sandbox_executable"] = True
            enabled.append(attack_id)
            family_surface[attack_id] = "payment"
            continue

        spec = SURFACE_TEMPLATES.get(surface)
        if not spec:
            still_blocked.append(attack_id)
            continue

        family["simulation_template_id"] = spec["template_id"]
        family["surface"] = surface
        family["technique_ids"] = [t.action_type for t in techniques]
        family["sandbox_executable"] = True
        enabled.append(attack_id)
        family_surface[attack_id] = surface

    fam_payload["built_at"] = datetime.now(timezone.utc).isoformat()
    fam_path.write_text(json.dumps(fam_payload, indent=2), encoding="utf-8")

    # --- vectors: migrate off the placeholder template --------------------------
    family_template = {
        f.get("attack_id"): f.get("simulation_template_id")
        for f in fam_payload["attack_families"]
        if f.get("attack_id") and f.get("simulation_template_id")
    }
    vec_stats = migrate_vectors(
        vec_payload["attack_vectors"], family_surface, family_template
    )
    vec_payload["built_at"] = datetime.now(timezone.utc).isoformat()
    vec_path.write_text(json.dumps(vec_payload, indent=2), encoding="utf-8")

    # --- relationships: repoint uses_template edges -----------------------------
    vector_template = {
        v["vector_id"]: v["simulation_template_id"]
        for v in vec_payload["attack_vectors"]
        if v.get("vector_id") and v.get("simulation_template_id")
    }
    rel_migrated = migrate_relationships(rel_payload["relationships"], vector_template)
    rel_payload["built_at"] = datetime.now(timezone.utc).isoformat()
    rel_path.write_text(json.dumps(rel_payload, indent=2), encoding="utf-8")

    families = fam_payload["attack_families"]
    executable = sum(1 for f in families if f.get("sandbox_executable"))
    print(f"templates: {len(templates)} (TPL-AGENTIC-NONEXEC removed)")
    for t in templates:
        if t.get("surface"):
            print(f"  {t['template_id']:16s} {t['supported_action_types']}")
    print()
    print(f"families flipped to executable via techniques: {len(enabled)}")
    print(f"  {sorted(enabled)}")
    print(f"executable total: {executable}/{len(families)}")
    vectors = vec_payload["attack_vectors"]
    vec_exec = sum(1 for v in vectors if v.get("sandbox_executable"))
    print(f"vectors migrated to surface templates: {vec_stats['migrated']}")
    print(f"vectors executable: {vec_exec}/{len(vectors)}")
    print(f"state requirements: {len(requirements)}")
    print(f"relationships repointed: {rel_migrated}")
    if still_blocked:
        print(f"STILL NOT EXECUTABLE ({len(still_blocked)}): {sorted(still_blocked)}")
        print("  -> no technique mapping in backend/taxonomy/techniques.py")


if __name__ == "__main__":
    main()
