#!/usr/bin/env python3
"""Validate the present KB while reporting, rather than requiring, canonical enrichment.

This intentionally uses only the standard library.  The canonical schemas describe
the target records; the current three legacy files are checked through compatible
projections so their missing future fields do not become errors.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "data" / "knowledge"
SCHEMAS = KNOWLEDGE / "schemas"


def load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def add(bucket: list[str], message: str) -> None:
    bucket.append(message)


def duplicates(values: list[str], label: str, errors: list[str]) -> None:
    for value, count in Counter(values).items():
        if value and count > 1:
            add(errors, f"duplicate {label}: {value!r} ({count} records)")


def validate() -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    required_schemas = {
        "attack_family.schema.json", "attack_vector.schema.json", "signal.schema.json",
        "lifecycle_stage.schema.json", "control.schema.json", "simulation_template.schema.json",
        "relationship.schema.json", "legitimate_counterpart.schema.json", "evidence.schema.json",
    }
    missing_schemas = required_schemas - {path.name for path in SCHEMAS.glob("*.schema.json")}
    for name in sorted(missing_schemas):
        add(errors, f"missing required schema: {name}")
    for path in SCHEMAS.glob("*.schema.json"):
        try:
            schema = load(path)
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                add(errors, f"{path.name}: unsupported or missing $schema")
        except (OSError, json.JSONDecodeError) as exc:
            add(errors, f"{path.name}: malformed JSON schema ({exc})")

    try:
        families_doc = load(KNOWLEDGE / "attack_families.json")
        signals_doc = load(KNOWLEDGE / "attack_signals.json")
        stages_doc = load(KNOWLEDGE / "lifecycle_stages.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"knowledge JSON cannot be read: {exc}"], warnings, {}

    families = families_doc.get("attack_families")
    signals = signals_doc.get("signals")
    stages = stages_doc.get("lifecycle_stages")
    for label, records in (("attack_families", families), ("signals", signals), ("lifecycle_stages", stages)):
        if not isinstance(records, list):
            add(errors, f"{label} must be an array")
    if errors:
        return errors, warnings, {}

    assert isinstance(families, list) and isinstance(signals, list) and isinstance(stages, list)
    duplicates([record.get("attack_id", "") for record in families if isinstance(record, dict)], "attack_id", errors)
    duplicates([record.get("stage_name", "") for record in stages if isinstance(record, dict)], "stage_name", errors)

    legacy_family_fields = {"attack_id", "name", "variants", "lifecycle_stage", "genai_classification", "simulation_type", "prerequisites", "attack_flow", "detection_signals", "controls_targeted", "evidence_confidence"}
    legacy_signal_fields = {"signal_name", "category", "description", "detection_method", "false_positive_risk", "cross_account_needed"}
    legacy_stage_fields = {"stage_name", "controls"}
    canonical_genai = {"traditional", "genai_amplified", "genai_load_bearing", "unknown"}
    legacy_genai = {"PASS", "PARTIAL"}
    known_stage_names = {record.get("stage_name", "").casefold() for record in stages if isinstance(record, dict)}

    for index, record in enumerate(families):
        prefix = f"family[{index}]"
        if not isinstance(record, dict):
            add(errors, f"{prefix} is not an object")
            continue
        missing = legacy_family_fields - set(record)
        if missing:
            add(errors, f"{prefix} missing legacy fields: {', '.join(sorted(missing))}")
        if not isinstance(record.get("attack_id"), str) or not record.get("attack_id", "").strip():
            add(errors, f"{prefix} has empty attack_id")
        if not isinstance(record.get("name"), str) or not record.get("name", "").strip():
            add(errors, f"{prefix} has empty name")
        if not isinstance(record.get("variants"), list) or not all(isinstance(v, str) and v.strip() for v in record.get("variants", [])):
            add(errors, f"{prefix} has an inconsistent variants structure")
        classification = record.get("genai_classification")
        if classification not in legacy_genai | canonical_genai:
            add(errors, f"{prefix} has malformed GenAI classification: {classification!r}")
        elif classification in legacy_genai:
            add(warnings, f"{prefix} uses legacy GenAI classification {classification!r}; map to traditional/genai_amplified/genai_load_bearing during enrichment")
        stage = record.get("lifecycle_stage")
        if not isinstance(stage, str) or not stage.strip():
            add(errors, f"{prefix} has an invalid lifecycle reference")
        elif stage.casefold() not in known_stage_names:
            add(warnings, f"{prefix} lifecycle stage {stage!r} has no exact stage_name record (legacy free-text reference)")
        for signal in record.get("detection_signals", []):
            if not isinstance(signal, dict) or not isinstance(signal.get("name"), str) or not signal["name"].strip():
                add(errors, f"{prefix} contains a malformed embedded signal")
        for field in ("objective", "lifecycle_stage_id", "cross_stage_lifecycle_stage_ids", "attacker", "target", "traditional_mechanism", "genai_transformation", "genai_load_bearing", "observable_signal_ids", "targeted_control_ids", "evidence"):
            if field not in record:
                add(warnings, f"{prefix} lacks future canonical field {field}")

    for index, record in enumerate(signals):
        prefix = f"signal[{index}]"
        if not isinstance(record, dict):
            add(errors, f"{prefix} is not an object")
            continue
        missing = legacy_signal_fields - set(record)
        if missing:
            add(errors, f"{prefix} missing legacy fields: {', '.join(sorted(missing))}")
        if not isinstance(record.get("signal_name"), str) or not record.get("signal_name", "").strip():
            add(errors, f"{prefix} has empty signal_name")
        if not isinstance(record.get("cross_account_needed"), bool):
            add(errors, f"{prefix} cross_account_needed must be boolean")
        add(warnings, f"{prefix} lacks stable signal_id; family-to-signal references remain fuzzy text matching")

    for index, record in enumerate(stages):
        prefix = f"stage[{index}]"
        if not isinstance(record, dict):
            add(errors, f"{prefix} is not an object")
            continue
        missing = legacy_stage_fields - set(record)
        if missing:
            add(errors, f"{prefix} missing legacy fields: {', '.join(sorted(missing))}")
        if not isinstance(record.get("stage_name"), str) or not record.get("stage_name", "").strip():
            add(errors, f"{prefix} has empty stage_name")
        if not isinstance(record.get("controls"), list) or not all(isinstance(item, str) and item.strip() for item in record.get("controls", [])):
            add(errors, f"{prefix} has an invalid controls structure")
        add(warnings, f"{prefix} lacks stable stage_id; controls are not independently referenceable")

    add(warnings, "No control registry exists, so control references cannot yet be validated.")
    add(warnings, "No canonical relationship records exist, so family/signal/control references are not machine-verifiable yet.")
    return errors, warnings, {"families": len(families), "signals": len(signals), "stages": len(stages)}


def main() -> int:
    errors, warnings, counts = validate()
    print("Knowledge validation")
    print(f"  families: {counts.get('families', 0)}")
    print(f"  signals: {counts.get('signals', 0)}")
    print(f"  lifecycle stages: {counts.get('stages', 0)}")
    print(f"  current-data errors: {len(errors)}")
    print(f"  future-enrichment warnings: {len(warnings)}")
    for label, messages in (("ERROR", errors), ("WARNING", warnings)):
        for message in messages:
            print(f"{label}: {message}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
