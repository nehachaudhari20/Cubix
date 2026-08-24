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


def load(filename: str, key: str) -> list[dict[str, Any]]:
    with (CANONICAL / filename).open(encoding="utf-8") as handle:
        value = json.load(handle).get(key)
    if not isinstance(value, list):
        raise ValueError(f"{filename}:{key} must be an array")
    return value


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
        families = load("attack_families.json", "attack_families")
        signals = load("signals.json", "signals")
        stages = load("lifecycle_stages.json", "lifecycle_stages")
        controls = load("controls.json", "controls")
        evidence = load("evidence.json", "evidence")
        relationships = load("relationships.json", "relationships")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    family_ids = unique(families, "attack_id", errors)
    signal_ids = unique(signals, "signal_id", errors)
    stage_ids = unique(stages, "stage_id", errors)
    control_ids = unique(controls, "control_id", errors)
    evidence_ids = unique(evidence, "evidence_id", errors)
    unique(relationships, "relationship_id", errors)
    known_refs = family_ids | signal_ids | stage_ids | control_ids
    allowed_genai = {"traditional", "genai_amplified", "genai_load_bearing", "unknown"}
    for family in families:
        required = {"attack_id", "name", "lifecycle_stage_id", "observable_signal_ids", "targeted_control_ids", "evidence", "genai_classification"}
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
        if family.get("genai_classification") not in allowed_genai:
            errors.append(f"family {family.get('attack_id')}: invalid GenAI classification")
    for control in controls:
        for identifier in control.get("lifecycle_stage_ids", []) + control.get("detects_signal_ids", []):
            if identifier not in (stage_ids | signal_ids):
                errors.append(f"control {control.get('control_id')}: dangling reference {identifier}")
    for relationship in relationships:
        if relationship.get("from_ref") not in known_refs or relationship.get("to_ref") not in known_refs:
            errors.append(f"relationship {relationship.get('relationship_id')}: dangling endpoint")
        if relationship.get("relationship_type") not in {"targets", "observes", "mitigates", "occurs_at", "crosses", "has_counterpart", "implemented_by"}:
            errors.append(f"relationship {relationship.get('relationship_id')}: invalid type")
        for identifier in relationship.get("evidence", []):
            if identifier not in evidence_ids:
                errors.append(f"relationship {relationship.get('relationship_id')}: dangling evidence")
    print("Canonical knowledge validation")
    print(f"  families: {len(families)} signals: {len(signals)} stages: {len(stages)} controls: {len(controls)}")
    print(f"  evidence: {len(evidence)} relationships: {len(relationships)} errors: {len(errors)}")
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
