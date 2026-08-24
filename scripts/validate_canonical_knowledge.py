#!/usr/bin/env python3
"""Referential-integrity validation for canonical KB registries."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "knowledge" / "canonical"

ALLOWED_REL = {
    "targets", "observes", "mitigates", "occurs_at", "crosses", "has_counterpart",
    "implemented_by", "variant_of", "instantiates", "uses_template", "parameterizes",
    "maps_to_feature", "precedes", "enables", "composes_with", "bypasses", "escalates_to",
}
ALLOWED_GENAI = {"traditional", "genai_amplified", "genai_load_bearing", "unknown"}


def load(path: Path, key: str) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle).get(key)
    if not isinstance(value, list):
        raise ValueError(f"{path}:{key} must be an array")
    return value


def pick(nested: str, flat: str, key: str) -> list[dict[str, Any]]:
    nested_path = CANONICAL / nested
    if nested_path.exists():
        return load(nested_path, key)
    return load(CANONICAL / flat, key)


def unique(records: list[dict[str, Any]], key: str, errors: list[str]) -> set[str]:
    values = [record.get(key) for record in records]
    for value, count in Counter(values).items():
        if not isinstance(value, str) or not value.strip():
            errors.append(f"empty {key}")
        elif count > 1:
            errors.append(f"duplicate {key}: {value}")
    return {value for value in values if isinstance(value, str) and value.strip()}


def main() -> int:
    errors: list[str] = []
    try:
        families = pick("attacks/attack_families.json", "attacks/attack_families.json", "attack_families")
        variants = pick("attacks/attack_variants.json", "attacks/attack_variants.json", "attack_variants")
        vectors = pick("attacks/attack_vectors.json", "attacks/attack_vectors.json", "attack_vectors")
        signals = pick("defense/signals.json", "defense/signals.json", "signals")
        stages = pick("lifecycle/lifecycle_stages.json", "lifecycle/lifecycle_stages.json", "lifecycle_stages")
        controls = pick("defense/controls.json", "defense/controls.json", "controls")
        evidence = pick("evidence/evidence.json", "evidence/evidence.json", "evidence")
        relationships = pick("attacks/attack_relationships.json", "attacks/attack_relationships.json", "relationships")
        templates = pick("simulation/simulation_templates.json", "simulation/simulation_templates.json", "simulation_templates")
        parameters = pick("simulation/parameters.json", "simulation/parameters.json", "parameters")
        counterparts = pick("simulation/legitimate_counterparts.json", "simulation/legitimate_counterparts.json", "legitimate_counterparts")
        capabilities = pick("genai/capabilities.json", "genai/capabilities.json", "capabilities")
        mappings = pick("defense/signal_feature_mappings.json", "defense/signal_feature_mappings.json", "signal_feature_mappings")
        requirements = pick("simulation/state_requirements.json", "simulation/state_requirements.json", "state_requirements")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    family_ids = unique(families, "attack_id", errors)
    variant_ids = unique(variants, "variant_id", errors)
    vector_ids = unique(vectors, "vector_id", errors)
    signal_ids = unique(signals, "signal_id", errors)
    stage_ids = unique(stages, "stage_id", errors)
    control_ids = unique(controls, "control_id", errors)
    evidence_ids = unique(evidence, "evidence_id", errors)
    template_ids = unique(templates, "template_id", errors)
    parameter_ids = unique(parameters, "parameter_id", errors)
    counterpart_ids = unique(counterparts, "counterpart_id", errors)
    capability_ids = unique(capabilities, "capability_id", errors)
    mapping_ids = unique(mappings, "mapping_id", errors)
    requirement_ids = unique(requirements, "requirement_id", errors)
    unique(relationships, "relationship_id", errors)

    known_refs = (
        family_ids | variant_ids | vector_ids | signal_ids | stage_ids | control_ids
        | template_ids | parameter_ids | counterpart_ids | capability_ids
        | mapping_ids | requirement_ids
    )

    for family in families:
        required = {
            "attack_id", "name", "lifecycle_stage_id", "observable_signal_ids",
            "targeted_control_ids", "evidence", "genai_classification",
        }
        missing = required - set(family)
        if missing:
            errors.append(f"family {family.get('attack_id')}: missing {sorted(missing)}")
        if family.get("lifecycle_stage_id") not in stage_ids:
            errors.append(f"family {family.get('attack_id')}: dangling lifecycle stage")
        for identifier in family.get("cross_stage_lifecycle_stage_ids", []) + family.get("observable_signal_ids", []) + family.get("targeted_control_ids", []):
            if identifier not in (stage_ids | signal_ids | control_ids):
                errors.append(f"family {family.get('attack_id')}: dangling reference {identifier}")
        for identifier in family.get("evidence", []):
            if identifier not in evidence_ids:
                errors.append(f"family {family.get('attack_id')}: dangling evidence {identifier}")
        for identifier in family.get("variant_ids", []):
            if identifier not in variant_ids:
                errors.append(f"family {family.get('attack_id')}: dangling variant {identifier}")
        genai = family.get("genai") or {}
        classification = genai.get("classification") or family.get("genai_classification")
        if classification not in ALLOWED_GENAI:
            errors.append(f"family {family.get('attack_id')}: invalid GenAI classification")
        for identifier in genai.get("capability_ids", []):
            if identifier not in capability_ids:
                errors.append(f"family {family.get('attack_id')}: dangling capability {identifier}")
        if "is_genai" in family:
            errors.append(f"family {family.get('attack_id')}: must not reduce GenAI to is_genai")

    for variant in variants:
        if variant.get("family_id") not in family_ids:
            errors.append(f"variant {variant.get('variant_id')}: dangling family")
        if variant.get("origin") not in {"source_backed", "implementation_derived"}:
            errors.append(f"variant {variant.get('variant_id')}: invalid origin")

    for vector in vectors:
        if vector.get("family_id") not in family_ids:
            errors.append(f"vector {vector.get('vector_id')}: dangling family")
        variant_id = vector.get("variant_id") or vector.get("variant_ref")
        if variant_id and variant_id not in variant_ids:
            errors.append(f"vector {vector.get('vector_id')}: dangling variant")
        template_id = vector.get("simulation_template_id") or vector.get("simulation_template_ref")
        if template_id and template_id not in template_ids:
            errors.append(f"vector {vector.get('vector_id')}: dangling template")
        if "amount" in vector and isinstance(vector.get("amount"), (int, float)):
            errors.append(f"vector {vector.get('vector_id')}: concrete amount is an instance field")
        if vector.get("timestamp"):
            errors.append(f"vector {vector.get('vector_id')}: timestamp is an instance field")
        actions = vector.get("ordered_actions") or []
        if not actions:
            errors.append(f"vector {vector.get('vector_id')}: missing ordered_actions")

    for mapping in mappings:
        if mapping.get("signal_id") not in signal_ids:
            errors.append(f"mapping {mapping.get('mapping_id')}: dangling signal")

    for control in controls:
        for identifier in control.get("lifecycle_stage_ids", []) + control.get("detects_signal_ids", []):
            if identifier not in (stage_ids | signal_ids):
                errors.append(f"control {control.get('control_id')}: dangling reference {identifier}")

    for relationship in relationships:
        rel_type = relationship.get("relationship_type")
        if rel_type not in ALLOWED_REL:
            errors.append(f"relationship {relationship.get('relationship_id')}: invalid type")
        from_ref = relationship.get("from_ref")
        to_ref = relationship.get("to_ref")
        if from_ref not in known_refs:
            errors.append(f"relationship {relationship.get('relationship_id')}: dangling from_ref {from_ref}")
        if rel_type == "implemented_by":
            if not (isinstance(to_ref, str) and to_ref.startswith("sandbox:")):
                errors.append(f"relationship {relationship.get('relationship_id')}: implemented_by must point at sandbox:*")
        elif to_ref not in known_refs:
            errors.append(f"relationship {relationship.get('relationship_id')}: dangling to_ref {to_ref}")
        for identifier in relationship.get("evidence", []):
            if identifier not in evidence_ids:
                errors.append(f"relationship {relationship.get('relationship_id')}: dangling evidence")

    print("Canonical knowledge validation")
    print(
        f"  families: {len(families)} variants: {len(variants)} vectors: {len(vectors)} "
        f"signals: {len(signals)} stages: {len(stages)} controls: {len(controls)}"
    )
    print(
        f"  evidence: {len(evidence)} relationships: {len(relationships)} "
        f"templates: {len(templates)} parameters: {len(parameters)} mappings: {len(mappings)}"
    )
    print(f"  errors: {len(errors)}")
    for error in errors[:50]:
        print(f"ERROR: {error}")
    if len(errors) > 50:
        print(f"... {len(errors) - 50} more")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
