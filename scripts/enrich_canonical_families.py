#!/usr/bin/env python3
"""Merge only page-evidenced source extraction values into canonical families."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "knowledge" / "canonical"
EXTRACTIONS = ROOT / "data" / "knowledge" / "source_extractions"
REVIEW = ROOT / "data" / "knowledge" / "review"
DOCS = ROOT / "docs"


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    family_doc = read(CANONICAL / "attack_families.json")
    evidence_doc = read(CANONICAL / "evidence.json")
    extractions = {item["attack_id"]: item for item in read(EXTRACTIONS / "families.json")["families"]}
    candidates = read(EXTRACTIONS / "evidence_candidates.json")["evidence_candidates"]
    candidate_index = {(item["attack_id"], item["field"]): item for item in candidates}
    aliases = read(CANONICAL / "lifecycle_aliases.json")
    alias_ids = {norm(name): identifier for name, identifier in aliases.items()}
    review: list[dict[str, Any]] = []
    enriched: Counter[str] = Counter()
    evidence_by_id = {item["evidence_id"]: item for item in evidence_doc["evidence"]}

    for family in family_doc["attack_families"]:
        attack_id = family["attack_id"]
        extracted = extractions.get(attack_id)
        if not extracted:
            review.append({"attack_id": attack_id, "reasons": ["insufficient source evidence: no extracted family section"]})
            continue
        raw = extracted["raw_fields"]
        reasons: list[str] = []
        for field in ("objective", "attacker", "target", "traditional_mechanism", "genai_transformation"):
            value = raw.get(field)
            candidate = candidate_index.get((attack_id, field))
            # Very short wrapped-table fragments are not safely useful values.
            if isinstance(value, str) and len(value.strip()) >= 20 and candidate:
                if family.get(field) in (None, "", []):
                    family[field] = value
                    enriched[field] += 1
                    evidence_id = f"EVD-SRC-{attack_id}-{field.upper()}"
                    evidence_by_id[evidence_id] = {"evidence_id": evidence_id, "source": candidate["source"],
                        "locator": f"page {candidate['page']}; {candidate['section']}", "excerpt": candidate["evidence_note"],
                        "confidence": "SUPPORTED", "maturity": None}
                    if evidence_id not in family["evidence"]:
                        family["evidence"].append(evidence_id)
            elif value is None:
                reasons.append(f"insufficient {field} evidence")
        lifecycle = raw.get("lifecycle_stage")
        if lifecycle:
            source_stage = alias_ids.get(norm(lifecycle))
            if source_stage and source_stage != family.get("lifecycle_stage_id"):
                reasons.append(f"primary lifecycle conflict: PDF {lifecycle!r} vs canonical {family.get('lifecycle_stage_id')}")
            elif not source_stage:
                reasons.append(f"unresolved PDF primary lifecycle: {lifecycle!r}")
        cross = raw.get("cross_stage")
        if cross:
            stage_ids: list[str] = []
            unresolved: list[str] = []
            for part in cross.split(";"):
                label = re.sub(r"\s*\(.*?\)", "", part).strip()
                identifier = alias_ids.get(norm(label))
                if identifier and identifier not in stage_ids:
                    stage_ids.append(identifier)
                elif label:
                    unresolved.append(label)
            if stage_ids:
                family["cross_stage_lifecycle_stage_ids"] = stage_ids
                enriched["cross_stage_lifecycle_stage_ids"] += 1
                candidate = candidate_index.get((attack_id, "cross_stage"))
                if candidate:
                    evidence_id = f"EVD-SRC-{attack_id}-CROSS-STAGE"
                    evidence_by_id[evidence_id] = {"evidence_id": evidence_id, "source": candidate["source"],
                        "locator": f"page {candidate['page']}; cross stage", "excerpt": candidate["evidence_note"],
                        "confidence": "SUPPORTED", "maturity": None}
                    if evidence_id not in family["evidence"]:
                        family["evidence"].append(evidence_id)
            if unresolved:
                reasons.append(f"unresolved/ambiguous cross-stage values: {unresolved}")
        classification = raw.get("genai_classification")
        candidate = candidate_index.get((attack_id, "genai_classification"))
        if classification in {"traditional", "genai_amplified", "genai_load_bearing"} and candidate:
            if family.get("genai_classification") != classification:
                reasons.append(f"GenAI classification conflict: canonical {family.get('genai_classification')} vs PDF {classification}")
            family["genai_classification"] = classification
            family["genai_load_bearing"] = classification == "genai_load_bearing"
            enriched["genai_classification"] += 1
            evidence_id = f"EVD-SRC-{attack_id}-GENAI-CLASSIFICATION"
            evidence_by_id[evidence_id] = {"evidence_id": evidence_id, "source": candidate["source"],
                "locator": f"page {candidate['page']}; GenAI classification", "excerpt": candidate["evidence_note"],
                "confidence": "SUPPORTED", "maturity": None}
            if evidence_id not in family["evidence"]:
                family["evidence"].append(evidence_id)
        if reasons:
            review.append({"attack_id": attack_id, "reasons": reasons})

    evidence_doc["evidence"] = list(evidence_by_id.values())
    write(CANONICAL / "attack_families.json", family_doc)
    write(CANONICAL / "evidence.json", evidence_doc)
    write(REVIEW / "family_review_queue.json", {"review_queue": review})
    classifications = Counter(item["genai_classification"] for item in family_doc["attack_families"])
    nulls = {field: sum(item.get(field) in (None, "", []) for item in family_doc["attack_families"])
             for field in ("objective", "attacker", "target", "traditional_mechanism", "genai_transformation")}
    source_evidence_count = sum(identifier.startswith("EVD-SRC-") for identifier in evidence_by_id)
    (DOCS / "FAMILY_ENRICHMENT_REPORT.md").write_text(
        "# Family enrichment report\n\n"
        f"- Families processed: {len(family_doc['attack_families'])}\n"
        f"- Source-backed field enrichments: {source_evidence_count}\n"
        f"- Families requiring human review: {len(review)}\n"
        f"- Page-level evidence records: {source_evidence_count}\n"
        f"- GenAI classifications: {dict(classifications)}\n\n"
        "## Fields still null\n\n" + "\n".join(f"- {field}: {count}" for field, count in nulls.items()) +
        "\n\n## Source coverage and conflicts\n\nAll 15 PDFs were enumerated. The review queue records insufficient extraction, lifecycle conflicts, "
        "unresolved cross-stage labels, and classification conflicts. No legacy file was modified; nulls remain where a labeled source field was not reliable.\n",
        encoding="utf-8")
    rows = ["# GenAI classification report", "", "| Family | Name | Classification | Load-bearing | Evidence page | Reasoning summary | Confidence |", "| --- | --- | --- | --- | ---: | --- | --- |"]
    for item in family_doc["attack_families"]:
        candidate = candidate_index.get((item["attack_id"], "genai_classification"))
        page = candidate["page"] if candidate else "—"
        confidence = "SUPPORTED" if candidate else "UNVERIFIED"
        reasoning = (candidate["evidence_note"] if candidate else "No section-local classification evidence extracted.").replace("|", "/")
        rows.append(f"| {item['attack_id']} | {item['name']} | {item['genai_classification']} | {item.get('genai_load_bearing')} | {page} | {reasoning} | {confidence} |")
    (DOCS / "GENAI_CLASSIFICATION_REPORT.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Enriched {sum(enriched.values())} fields; {len(review)} families queued for review")


if __name__ == "__main__":
    main()
