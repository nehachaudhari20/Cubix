#!/usr/bin/env python3
"""Create an enriched family registry without overwriting the canonical source."""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "knowledge" / "canonical"
EXTRACTIONS = ROOT / "data" / "knowledge" / "source_extractions"
REVIEW = ROOT / "data" / "knowledge" / "review"
ENRICHABLE = ("objective", "attacker", "target", "traditional_mechanism", "genai_transformation", "variants", "prerequisites", "attack_flow", "simulation_type")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    legacy = load(CANONICAL / "attack_families.json")
    family_sources = {item["attack_id"]: item["sources"] for item in load(EXTRACTIONS / "family_evidence.json")["families"]}
    candidates = {(item["attack_id"], item["field"]): item for item in load(EXTRACTIONS / "evidence_candidates.json")["evidence_candidates"]}
    classifications = {item["attack_id"]: item for item in load(EXTRACTIONS / "genai_classifications.json")["classifications"]}
    enriched = copy.deepcopy(legacy)
    conflicts: list[dict[str, Any]] = []
    changes: Counter[str] = Counter()
    for family in enriched["attack_families"]:
        identifier = family["attack_id"]
        for field in ENRICHABLE:
            candidate = candidates.get((identifier, field))
            if not candidate:
                continue
            source_value, legacy_value = candidate["value"], family.get(field)
            if legacy_value in (None, "", []):
                family[field] = source_value
                changes[field] += 1
            elif legacy_value != source_value:
                conflicts.append({"attack_id": identifier, "field": field, "legacy_value": legacy_value, "source_value": source_value, "source": candidate["source"], "page": candidate["page"], "reason": "Existing canonical value differs from the source-labeled value; legacy value was preserved."})
        classification = classifications.get(identifier)
        if classification and classification["classification"] != "unknown":
            source_value, legacy_value = classification["classification"], family.get("genai_classification")
            if legacy_value not in (None, "", "unknown", source_value):
                evidence = classification.get("evidence", [{}])[0]
                conflicts.append({"attack_id": identifier, "field": "genai_classification", "legacy_value": legacy_value, "source_value": source_value, "source": evidence.get("source"), "page": evidence.get("page"), "reason": "Classification differs; legacy classification was preserved."})
            elif legacy_value in (None, "", "unknown"):
                family["genai_classification"], family["genai_load_bearing"] = source_value, classification["load_bearing"]
                changes["genai_classification"] += 1
    review = [{"attack_id": item["attack_id"], "field": None, "reason": "No source family pages were mapped."} for item in enriched["attack_families"] if not family_sources.get(item["attack_id"])]
    review.extend(conflicts)
    REVIEW.mkdir(parents=True, exist_ok=True)
    (REVIEW / "family_review_queue.json").write_text(json.dumps({"review_queue": review}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (CANONICAL / "attack_families_enriched.json").write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = ("objective", "attacker", "target", "traditional_mechanism", "genai_transformation", "genai_classification", "simulation_type", "variants", "prerequisites", "attack_flow", "observable_signal_ids", "targeted_control_ids")
    nulls = Counter(field for family in enriched["attack_families"] for field in fields if family.get(field) in (None, "", []))
    counts = Counter(family.get("genai_classification", "unknown") for family in enriched["attack_families"])
    families = enriched["attack_families"]
    coverage = {field: sum(bool(item.get(field)) for item in families) for field in ("objective", "attacker", "target", "traditional_mechanism", "genai_transformation")}
    report = ["# Family Enrichment Report", "", f"- total families: {len(families)}", f"- families with objective: {coverage['objective']}", f"- families without objective: {len(families) - coverage['objective']}", f"- families with attacker: {coverage['attacker']}", f"- families without attacker: {len(families) - coverage['attacker']}", f"- families with target: {coverage['target']}", f"- families without target: {len(families) - coverage['target']}", f"- families with traditional mechanism: {coverage['traditional_mechanism']}", f"- families with GenAI transformation: {coverage['genai_transformation']}", f"- families with explicit GenAI evidence: {sum(x['attack_id'] in classifications and classifications[x['attack_id']]['classification'] != 'unknown' for x in families)}", f"- families classified traditional: {counts['traditional']}", f"- families classified genai_amplified: {counts['genai_amplified']}", f"- families classified genai_load_bearing: {counts['genai_load_bearing']}", f"- families classified unknown: {counts['unknown']}", f"- families mapped to source pages: {sum(bool(family_sources.get(x['attack_id'])) for x in families)}", f"- families enriched: {sum(any(x.get(field) != legacy_family.get(field) for field in fields) for x, legacy_family in zip(families, legacy['attack_families']))}", f"- fields still null: {sum(nulls.values())}", f"- conflicts: {len(conflicts)}", f"- requiring human review: {len(review)}", "", "## Fields Still Null", "", "Null or empty values remain where the PDFs did not yield a reliable labeled value; no values were inferred."]
    report.extend(f"- {field}: {count}" for field, count in sorted(nulls.items()))
    (ROOT / "docs" / "FAMILY_ENRICHMENT_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    rows = ["# GenAI Classification Report", "", "| ID | Family | Classification | Load-bearing | Evidence | Confidence |", "| --- | --- | --- | --- | --- | --- |"]
    names = {x["attack_id"]: x["name"] for x in families}
    for identifier, item in sorted(classifications.items()):
        evidence = "; ".join(f"{e.get('source')} p.{e.get('page')} {e.get('section')}" for e in item.get("evidence", [])) or "No explicit source locator"
        rows.append(f"| {identifier} | {names.get(identifier, '')} | {item['classification']} | {item['load_bearing']} | {evidence} | {'SUPPORTED' if item['classification'] != 'unknown' else 'UNKNOWN'} |")
    (ROOT / "docs" / "GENAI_CLASSIFICATION_REPORT.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Created enriched registry: {len(families)} families, {sum(changes.values())} field changes, {len(conflicts)} conflicts, {len(review)} review items")


if __name__ == "__main__":
    main()
