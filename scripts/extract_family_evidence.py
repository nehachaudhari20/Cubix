#!/usr/bin/env python3
"""Extract page-preserving, source-backed evidence from the taxonomy PDFs."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw_pdfs"
OUT = ROOT / "data" / "knowledge" / "source_extractions"
CANONICAL = ROOT / "data" / "knowledge" / "canonical"
FIELD_LABELS = {
    "objective": ("Attack Objective", "Objective"), "attacker": ("Attacker", "Attacker Roles"),
    "target": ("Target / Actor", "Target"), "traditional_mechanism": ("Traditional mechanism", "Traditional Mechanism"),
    "genai_transformation": ("GenAI transformation", "GenAI Transformation"), "variants": ("Variants", "Attack Variants"),
    "prerequisites": ("Prerequisites", "Preconditions"), "attack_flow": ("Attack Flow", "Attack flow"),
    "simulation_type": ("Simulation Type", "Simulation"), "signals": ("Observable Signals", "Detection Signals", "Signals"),
    "controls": ("Targeted Controls", "Controls Targeted", "Controls"),
}
ID_PATTERN = re.compile(r"\b(?:[A-Z]{1,5}-[A-Z0-9]+(?:-[A-Z0-9]+)?)\b")


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00ad", "")).strip(" :\t")


def section_value(text: str, labels: tuple[str, ...]) -> str | None:
    alternatives = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?im)^\s*(?:{alternatives})\s*:\s*(.+?)(?=\n\s*[A-Z][^\n:]{1,70}:|\Z)", text, re.S)
    if not match:
        match = re.search(rf"(?im)\b(?:{alternatives})\b\s*:?\s*(.+?)(?=\n\s*[A-Z][^\n:]{1,70}:|\Z)", text, re.S)
    if not match:
        return None
    value = compact(match.group(1))
    return value[:1200] if len(value) >= 3 else None


def classification_for(identifier: str, pages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    contexts = []
    for page in pages:
        for match in re.finditer(re.escape(identifier), page["text"], re.I):
            contexts.append((page, page["text"][max(0, match.start() - 1200):match.end() + 1200]))
    evidence = []
    amplified = False
    for page, text in contexts:
        if re.search(r"genai\s+load[ -]?bearing|load[ -]?bearing\s+genai", text, re.I):
            return "genai_load_bearing", [{"source": page["source"], "page": page["page"], "section": "GenAI Analysis"}]
        if re.search(r"genai\s+amplif|amplif(?:ied|ication).*genai", text, re.I):
            amplified = True
            evidence.append({"source": page["source"], "page": page["page"], "section": "GenAI Analysis"})
        elif re.search(r"traditional\s*(?:only|attack)|no\s+genai|without\s+genai", text, re.I):
            evidence.append({"source": page["source"], "page": page["page"], "section": "GenAI Analysis"})
    if evidence:
        classification = "genai_amplified" if amplified else "traditional"
        return classification, evidence[:8]
    return "unknown", []


def source_fields(text: str) -> dict[str, Any]:
    values = {field: section_value(text, labels) for field, labels in FIELD_LABELS.items()}
    if re.search(r"genai\s+load[ -]?bearing|load[ -]?bearing\s+genai", text, re.I):
        values["genai_classification"] = "genai_load_bearing"
    elif re.search(r"genai\s+amplif|amplif(?:ied|ication).*genai", text, re.I):
        values["genai_classification"] = "genai_amplified"
    elif re.search(r"traditional\s*(?:only|attack)|no\s+genai|without\s+genai", text, re.I):
        values["genai_classification"] = "traditional"
    else:
        values["genai_classification"] = "unknown"
    return values


def main() -> None:
    families = json.loads((CANONICAL / "attack_families.json").read_text(encoding="utf-8"))["attack_families"]
    family_ids = {item["attack_id"] for item in families}
    pages: list[dict[str, Any]] = []
    pdf_map: list[dict[str, Any]] = []
    for pdf in sorted(PDF_DIR.glob("*.pdf")):
        reader = PdfReader(str(pdf))
        texts = []
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            texts.append(text)
            pages.append({"source": pdf.name, "page": page_number, "text": text})
        pdf_map.append({"source": pdf.name, "pages": len(reader.pages), "family_ids": sorted(set(ID_PATTERN.findall("\n".join(texts))) & family_ids)})

    matches = {identifier: [page for page in pages if identifier in set(ID_PATTERN.findall(page["text"]))] for identifier in family_ids}
    family_records = []
    candidates = []
    classifications = []
    for family in families:
        identifier = family["attack_id"]
        evidence_pages = matches[identifier]
        grouped: dict[str, list[int]] = {}
        for page in evidence_pages:
            grouped.setdefault(page["source"], []).append(page["page"])
        family_records.append({"attack_id": identifier, "sources": [{"source": source, "pages": sorted(numbers), "sections": []} for source, numbers in sorted(grouped.items())]})
        fields = source_fields("\n".join(page["text"] for page in evidence_pages)) if evidence_pages else {}
        classification, classification_evidence = classification_for(identifier, evidence_pages)
        classifications.append({"attack_id": identifier, "classification": classification, "load_bearing": True if classification == "genai_load_bearing" else False if classification in {"traditional", "genai_amplified"} else None, "reason": "Explicit source terminology matched in family pages." if classification != "unknown" else "No sufficiently explicit classification terminology was found in the family pages.", "evidence": classification_evidence[:8]})
        if evidence_pages:
            first = evidence_pages[0]
            for field, value in fields.items():
                if value in (None, "", []):
                    continue
                candidates.append({"evidence_id": f"EVC-{identifier}-{field.upper()}", "source": first["source"], "page": first["page"], "section": field.replace("_", " "), "attack_id": identifier, "field": field, "evidence_type": "labeled_source_section", "short_evidence_note": compact(str(value))[:280], "value": value, "confidence": "SUPPORTED"})
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in {"pages.json": {"pages": pages}, "family_evidence.json": {"families": family_records}, "evidence_candidates.json": {"evidence_candidates": candidates}, "genai_classifications.json": {"classifications": classifications}}.items():
        (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# PDF Taxonomy Map", "", "Source structure derived from the original PDFs using page-preserving extraction.", ""]
    for item in pdf_map:
        lines += [f"## {item['source']}", "", f"- pages: {item['pages']}", f"- family IDs: {', '.join(item['family_ids']) or 'none detected'}", "- relevant sections: family identity tables and labeled family analysis sections", "- GenAI section: detected within family pages where present", "- simulation section: detected within family pages where present", "- signals: detected within family pages where present", "- controls: detected within family pages where present", ""]
    (ROOT / "docs" / "PDF_TAXONOMY_MAP.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Extracted {len(pdf_map)} PDFs, {len(pages)} pages, and mapped {sum(bool(value) for value in matches.values())} families to source pages")


if __name__ == "__main__":
    main()
