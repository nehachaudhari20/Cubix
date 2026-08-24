#!/usr/bin/env python3
"""Extract conservative, page-level taxonomy evidence without mutating KB data."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw_pdfs"
OUT = ROOT / "data" / "knowledge" / "source_extractions"
CANONICAL = ROOT / "data" / "knowledge" / "canonical" / "attack_families.json"
EVIDENCE = ROOT / "data" / "knowledge" / "canonical" / "evidence.json"
FIELD_LABELS = {
    "objective": ("Attack Objective", "Objective"),
    "attacker": ("Attacker", "Attacker Roles"),
    "target": ("Target / Actor", "Target"),
    "lifecycle_stage": ("Primary Lifecycle Stage", "Primary Lifecycle", "Lifecycle Stage"),
    "cross_stage": ("Secondary / Cross-stage Stages", "Secondary / Cross-", "Cross-stage Stages", "Cross-stage"),
    "traditional_mechanism": ("Traditional mechanism",),
    "genai_transformation": ("GenAI transformation",),
}


def pdf_tool() -> str:
    found = shutil.which("pdftotext")
    fallback = Path(r"C:\Program Files\Git\mingw64\bin\pdftotext.exe")
    if found:
        return found
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("pdftotext is required to extract page-level evidence")


def page_texts(pdf: Path) -> list[str]:
    tool = pdf_tool()
    probe = subprocess.run([tool, "-f", "1", "-l", "9999", "-layout", str(pdf), "-"], capture_output=True, check=False)
    # Form-feed is produced between PDF pages; decoding replacement avoids source-text loss.
    return probe.stdout.decode("utf-8", errors="replace").split("\f") if probe.returncode == 0 else []


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00ad", "")).strip(" :-\t")


def family_starts(pages: list[str]) -> list[tuple[str, int, int]]:
    starts: list[tuple[str, int, int]] = []
    pattern = re.compile(r"(?:FAMILY\s+[^\n]{0,100}?\b|FAMILY\s+\d+[^\n]{0,100}?\()([A-Z]{1,4}(?:-[A-Z0-9]+)+)\b", re.I)
    for page_no, page in enumerate(pages, 1):
        for match in pattern.finditer(page):
            starts.append((match.group(1).upper(), page_no, match.start()))
    return starts


def excerpt_for(label: str, text: str) -> str | None:
    for option in FIELD_LABELS[label]:
        match = re.search(rf"\b{re.escape(option)}\b\s*[:]?\s*(.+)", text, re.I)
        if match:
            value = clean(match.group(1))
            if value and len(value) > 5:
                return value[:900]
    return None


def section_text(start: int, end: int, text: str) -> str | None:
    match = re.search(rf"\b{re.escape(start)}\b\s*[:]?\s*(.*?)(?=\b{re.escape(end)}\b|\Z)", text, re.I | re.S)
    return clean(match.group(1))[:1600] if match and clean(match.group(1)) else None


def extract(attack_id: str, source: str, pages: list[str], first_page: int, first_offset: int, next_page: int | None) -> dict[str, Any]:
    # A document can contain two family headings on one page. Keep the current
    # page in that case; the heading offset still provides a safe lower bound.
    end = next_page - 1 if next_page and next_page > first_page else len(pages)
    selected = pages[first_page - 1:end]
    selected[0] = selected[0][first_offset:]
    text = "\n".join(selected)
    raw: dict[str, Any] = {key: None for key in FIELD_LABELS}
    for field in ("objective", "attacker", "target", "lifecycle_stage", "cross_stage"):
        raw[field] = excerpt_for(field, text)
    raw["traditional_mechanism"] = section_text("Traditional mechanism", "GenAI transformation", text)
    raw["genai_transformation"] = section_text("GenAI transformation", "If GenAI is removed", text)
    raw["genai_classification"] = "genai_load_bearing" if re.search(r"why (?:agentic ai|genai|ai) is load[ -]bearing|genai load[ -]bearing", text, re.I) else ("genai_amplified" if raw["genai_transformation"] else "unknown")
    raw["signals"] = None
    raw["controls"] = None
    raw["variants"] = None  # The legacy registry already preserves variants; table parsing is intentionally deferred.
    return {"attack_id": attack_id, "source": source, "pages": list(range(first_page, first_page + len(selected))),
            "sections": [key for key, value in raw.items() if value], "raw_fields": raw}


def main() -> None:
    canonical_ids = {item["attack_id"] for item in json.loads(CANONICAL.read_text(encoding="utf-8"))["attack_families"]}
    source_by_id = {item["evidence_id"].removeprefix("EVD-"): item["source"]
                    for item in json.loads(EVIDENCE.read_text(encoding="utf-8"))["evidence"]
                    if item.get("evidence_id", "").startswith("EVD-") and "-" in item["evidence_id"][4:] and
                    item["evidence_id"].count("-") == 2}
    extracted: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for pdf in sorted(PDF_DIR.glob("*.pdf")):
        pages = page_texts(pdf)
        starts = [(identifier, page, offset) for identifier, page, offset in family_starts(pages) if identifier in canonical_ids]
        found = {identifier for identifier, _, _ in starts}
        # Some PDFs use non-standard headings (for example ``FAMILY 1: ...
        # (AUTH-001)``). Fall back to the first occurrence only for the PDF
        # already recorded as that family's source, never across documents.
        for attack_id in sorted(canonical_ids - found):
            if source_by_id.get(attack_id) != pdf.name:
                continue
            marker = re.compile(rf"\b{re.escape(attack_id)}\b", re.I)
            for page_no, page_text in enumerate(pages, 1):
                match = marker.search(page_text)
                if match:
                    starts.append((attack_id, page_no, match.start()))
                    break
        starts.sort(key=lambda item: (item[1], item[2]))
        for index, (attack_id, page, offset) in enumerate(starts):
            next_page = starts[index + 1][1] if index + 1 < len(starts) else None
            record = extract(attack_id, pdf.name, pages, page, offset, next_page)
            extracted.append(record)
            for field, value in record["raw_fields"].items():
                if value is None or field in {"signals", "controls", "variants"}:
                    continue
                candidates.append({"candidate_id": f"CND-{attack_id}-{field.upper()}", "attack_id": attack_id,
                                   "source": pdf.name, "page": page, "section": field.replace("_", " "),
                                   "field": field, "value": value, "evidence_note": clean(str(value))[:280]})
    # Repeated headings in summary tables are not distinct source family
    # sections. Keep the first full section for each canonical ID.
    by_id: dict[str, dict[str, Any]] = {}
    for record in extracted:
        by_id.setdefault(record["attack_id"], record)
    extracted = list(by_id.values())
    allowed = {record["attack_id"] for record in extracted}
    candidates = [candidate for candidate in candidates if candidate["attack_id"] in allowed and
                  candidate["source"] == by_id[candidate["attack_id"]]["source"] and
                  candidate["page"] == by_id[candidate["attack_id"]]["pages"][0]]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "families.json").write_text(json.dumps({"families": extracted}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "evidence_candidates.json").write_text(json.dumps({"evidence_candidates": candidates}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Extracted {len(extracted)} family records and {len(candidates)} evidence candidates from {len(list(PDF_DIR.glob('*.pdf')))} PDFs")


if __name__ == "__main__":
    main()
