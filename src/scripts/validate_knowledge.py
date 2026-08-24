#!/usr/bin/env python3
"""Validate canonical KB and runtime projection via KnowledgeLoader."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
KNOWLEDGE = ROOT / "data" / "knowledge"
CANONICAL = KNOWLEDGE / "canonical"
SCHEMAS = KNOWLEDGE / "schemas"

sys.path.insert(0, str(SRC))
from backend.knowledge.loader import KnowledgeLoader  # noqa: E402


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
        families_doc = load(CANONICAL / "attacks" / "attack_families.json")
        signals_doc = load(CANONICAL / "defense" / "signals.json")
        stages_doc = load(CANONICAL / "lifecycle" / "lifecycle_stages.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"canonical knowledge JSON cannot be read: {exc}"], warnings, {}

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
    duplicates([record.get("signal_id", "") for record in signals if isinstance(record, dict)], "signal_id", errors)
    duplicates([record.get("stage_id", "") for record in stages if isinstance(record, dict)], "stage_id", errors)

    canonical_genai = {"traditional", "genai_amplified", "genai_load_bearing", "unknown"}
    legacy_genai = {"PASS", "PARTIAL"}
    stage_ids = {record.get("stage_id") for record in stages if isinstance(record, dict) and record.get("stage_id")}
    signal_ids = {record.get("signal_id") for record in signals if isinstance(record, dict) and record.get("signal_id")}

    for index, record in enumerate(families):
        prefix = f"family[{index}]"
        if not isinstance(record, dict):
            add(errors, f"{prefix} is not an object")
            continue
        if not isinstance(record.get("attack_id"), str) or not record.get("attack_id", "").strip():
            add(errors, f"{prefix} has empty attack_id")
        if not isinstance(record.get("name"), str) or not record.get("name", "").strip():
            add(errors, f"{prefix} has empty name")
        if not isinstance(record.get("variants"), list):
            add(errors, f"{prefix} has an inconsistent variants structure")
        classification = record.get("genai_classification")
        if classification not in legacy_genai | canonical_genai:
            add(errors, f"{prefix} has malformed GenAI classification: {classification!r}")
        stage_id = record.get("lifecycle_stage_id")
        if not isinstance(stage_id, str) or not stage_id.strip():
            add(errors, f"{prefix} has an invalid lifecycle_stage_id")
        elif stage_id not in stage_ids:
            add(errors, f"{prefix} lifecycle_stage_id {stage_id!r} not found in stages registry")
        for signal_id in record.get("observable_signal_ids") or []:
            if signal_id not in signal_ids:
                add(warnings, f"{prefix} references unknown signal_id {signal_id!r}")

    for index, record in enumerate(signals):
        prefix = f"signal[{index}]"
        if not isinstance(record, dict):
            add(errors, f"{prefix} is not an object")
            continue
        if not isinstance(record.get("signal_id"), str) or not record.get("signal_id", "").strip():
            add(errors, f"{prefix} has empty signal_id")
        if not isinstance(record.get("name"), str) or not record.get("name", "").strip():
            add(errors, f"{prefix} has empty name")
        if not isinstance(record.get("cross_account_needed"), bool):
            add(errors, f"{prefix} cross_account_needed must be boolean")

    for index, record in enumerate(stages):
        prefix = f"stage[{index}]"
        if not isinstance(record, dict):
            add(errors, f"{prefix} is not an object")
            continue
        if not isinstance(record.get("stage_id"), str) or not record.get("stage_id", "").strip():
            add(errors, f"{prefix} has empty stage_id")
        if not isinstance(record.get("name"), str) or not record.get("name", "").strip():
            add(errors, f"{prefix} has empty name")
        if not isinstance(record.get("controls"), list) or not all(isinstance(item, str) and item.strip() for item in record.get("controls", [])):
            add(errors, f"{prefix} has an invalid controls structure")

    if not (CANONICAL / "defense" / "controls.json").exists():
        add(warnings, "No control registry exists, so control references cannot yet be validated.")

    loader = KnowledgeLoader(str(KNOWLEDGE))
    legacy_family_fields = {"attack_id", "name", "variants", "lifecycle_stage", "genai_classification", "simulation_type", "prerequisites", "attack_flow", "detection_signals", "controls_targeted", "evidence_confidence"}
    legacy_signal_fields = {"signal_name", "category", "description", "detection_method", "false_positive_risk", "cross_account_needed"}
    legacy_stage_fields = {"stage_name", "controls"}
    known_stage_names = {
        (record.get("stage_name") or record.get("name") or "").casefold()
        for record in loader.stages if isinstance(record, dict)
    }

    for index, record in enumerate(loader.families):
        prefix = f"runtime_family[{index}]"
        missing = legacy_family_fields - set(record)
        if missing:
            add(errors, f"{prefix} missing runtime aliases: {', '.join(sorted(missing))}")
        stage = record.get("lifecycle_stage")
        if not isinstance(stage, str) or not stage.strip():
            add(errors, f"{prefix} has an invalid hydrated lifecycle_stage")
        elif stage.casefold() not in known_stage_names:
            add(errors, f"{prefix} lifecycle stage {stage!r} not found in hydrated stages")

    for index, record in enumerate(loader.signals):
        prefix = f"runtime_signal[{index}]"
        missing = legacy_signal_fields - set(record)
        if missing:
            add(errors, f"{prefix} missing runtime aliases: {', '.join(sorted(missing))}")

    for index, record in enumerate(loader.stages):
        prefix = f"runtime_stage[{index}]"
        missing = legacy_stage_fields - set(record)
        if missing:
            add(errors, f"{prefix} missing runtime aliases: {', '.join(sorted(missing))}")

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
