#!/usr/bin/env python3
"""Build canonical registry files from the immutable legacy KB and taxonomy PDFs.

This is a one-way normalization utility.  It does not modify legacy KB inputs
or any runtime consumer, and it deliberately leaves unsupported source fields
null rather than manufacturing values.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "data" / "knowledge"
OUT = LEGACY / "canonical"
PDF_TEXT = ROOT / ".tmp_pdf_text"

PREFIX_SOURCE = {
    "AG": "agent-commerce-11.pdf", "AML": "aml-14.pdf", "ACQ": "aquirer-7.pdf",
    "AUTH": "authentication-4.pdf", "AUT": "authorization-10.pdf", "CM": "cash-out-13.pdf",
    "DFS": "device-session-3.pdf", "EFF": "device-session-3.pdf", "RAT": "device-session-3.pdf",
    "BOT": "device-session-3.pdf", "BBE": "device-session-3.pdf", "GP": "gateway-processor-8.pdf",
    "SIF": "KYC-1.pdf", "GDF": "KYC-1.pdf", "DII": "KYC-1.pdf", "SEP": "KYC-1.pdf",
    "ATO-001": "KYC-1.pdf", "ATO-002": "onboarding-2.pdf", "N": "network-15.pdf",
    "SIA": "onboarding-2.pdf", "MDF": "onboarding-2.pdf", "OB": "open-banking-12.pdf",
    "PI": "payment-inititation-5.pdf", "R": "payment-rail-9.pdf", "MCH": "merchant-6.pdf",
}


def read_json(name: str) -> dict[str, Any]:
    return json.loads((LEGACY / name).read_text(encoding="utf-8"))


def write_json(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def source_for(attack_id: str) -> str | None:
    return PREFIX_SOURCE.get(attack_id) or PREFIX_SOURCE.get(attack_id.split("-", 1)[0])


def source_section(attack_id: str, source: str | None) -> str:
    if not source:
        return ""
    text_path = PDF_TEXT / (Path(source).stem + ".txt")
    if text_path.exists():
        text = text_path.read_text(encoding="utf-8", errors="ignore")
    else:
        executable = shutil.which("pdftotext")
        git_pdftext = Path(r"C:\Program Files\Git\mingw64\bin\pdftotext.exe")
        if not executable and git_pdftext.exists():
            executable = str(git_pdftext)
        pdf = ROOT / "data" / "raw_pdfs" / source
        if not executable or not pdf.exists():
            return ""
        result = subprocess.run([executable, "-layout", str(pdf), "-"], capture_output=True, check=False)
        text = result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else ""
    match = re.search(rf"(?:FAMILY\s+[^\n]*\b{re.escape(attack_id)}\b|\b{re.escape(attack_id)}\b)", text, re.I)
    if not match:
        return ""
    tail = text[match.start():]
    next_family = re.search(r"\n\s*FAMILY\s+[^\n]*\b[A-Z]{1,4}(?:-[A-Z0-9]+)+\b", tail[40:], re.I)
    return tail[:40 + next_family.start()] if next_family else tail[:14000]


def classification(attack_id: str, source: str | None) -> tuple[str, bool | None, str]:
    """Classify only from the section-local source language, never PASS/PARTIAL."""
    section = source_section(attack_id, source).casefold()
    if re.search(r"why (?:agentic ai|genai|ai) is load[ -]bearing|genai load[ -]bearing", section):
        return "genai_load_bearing", True, "Source section explicitly describes GenAI/agentic AI as load-bearing."
    if "genai transformation" in section:
        return "genai_amplified", False, "Source section describes a GenAI transformation but not load-bearing language."
    return "unknown", None, "No section-local classification language extracted."


def stage_candidates(value: str, stages: list[dict[str, Any]]) -> list[str]:
    needle = norm(value)
    exact = [stage["stage_id"] for stage in stages if norm(stage["name"]) == needle]
    if exact:
        return exact
    tokens = set(needle.split())
    ranked: list[tuple[float, str]] = []
    for stage in stages:
        candidate = set(norm(stage["name"]).split())
        overlap = len(tokens & candidate) / max(1, len(tokens | candidate))
        if norm(stage["name"]) in needle or needle in norm(stage["name"]):
            overlap += 1
        ranked.append((overlap, stage["stage_id"]))
    ranked.sort(reverse=True)
    return [ranked[0][1]] if ranked and ranked[0][0] >= 0.30 else []


def main() -> None:
    families = read_json("attack_families.json")["attack_families"]
    signals = read_json("attack_signals.json")["signals"]
    legacy_stages = read_json("lifecycle_stages.json")["lifecycle_stages"]

    # Exact normalized duplicate stage names represent alternate source control lists.
    stage_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for legacy in legacy_stages:
        stage_groups[norm(legacy["stage_name"])].append(legacy)
    stages: list[dict[str, Any]] = []
    lifecycle_aliases: dict[str, str] = {}
    for index, group in enumerate(stage_groups.values(), 1):
        first = group[0]
        controls = list(dict.fromkeys(control for item in group for control in item["controls"]))
        stage_id = f"STG-{index:04d}"
        stage = {"stage_id": stage_id, "name": first["stage_name"], "sequence": None,
                 "controls": controls, "evidence": []}
        number = re.search(r"Stage\s+(\d+)", first["stage_name"], re.I)
        if number:
            stage["sequence"] = int(number.group(1))
        stages.append(stage)
        for item in group:
            lifecycle_aliases[item["stage_name"]] = stage_id
    # Each legacy family stage is also an alias when it can be resolved deterministically.
    unresolved_stages: list[str] = []
    for family in families:
        resolved = stage_candidates(family["lifecycle_stage"], stages)
        if len(resolved) == 1:
            lifecycle_aliases[family["lifecycle_stage"]] = resolved[0]
        else:
            unresolved_stages.append(family["lifecycle_stage"])
    # The network taxonomy supplies this primary stage even though the legacy
    # lifecycle file omitted it.  Preserve it as a source-derived stage rather
    # than force a network family onto an unrelated single-stage record.
    for name in sorted(set(unresolved_stages)):
        if norm(name) in {"cross stage network"}:
            stage_id = f"STG-{len(stages) + 1:04d}"
            stages.append({"stage_id": stage_id, "name": name, "sequence": None, "controls": [], "evidence": []})
            lifecycle_aliases[name] = stage_id
    unresolved_stages = [name for name in unresolved_stages if name not in lifecycle_aliases]
    write_json("lifecycle_stages.json", {"registry_version": "1.0", "lifecycle_stages": stages})
    write_json("lifecycle_aliases.json", lifecycle_aliases)

    canonical_signals: list[dict[str, Any]] = []
    signal_aliases: dict[str, str] = {}
    duplicate_signal_names: list[str] = []
    for index, signal in enumerate(signals, 1):
        signal_id = f"SIG-{index:04d}"
        methods = [part.strip() for part in signal["detection_method"].split(";") if part.strip()]
        canonical_signals.append({
            "signal_id": signal_id, "name": signal["signal_name"], "category": signal["category"],
            "description": signal["description"], "detection_methods": methods,
            "false_positive_risk": signal["false_positive_risk"],
            "cross_account_needed": signal["cross_account_needed"], "evidence": [],
        })
        key = norm(signal["signal_name"])
        if key in signal_aliases:
            duplicate_signal_names.append(signal["signal_name"])
        else:
            signal_aliases[key] = signal_id
    unresolved_signal_aliases: list[str] = []
    for family in families:
        for signal in family["detection_signals"]:
            key = norm(signal["name"])
            if key not in signal_aliases:
                unresolved_signal_aliases.append(signal["name"])
    write_json("signals.json", {"registry_version": "1.0", "signals": canonical_signals})
    write_json("signal_aliases.json", signal_aliases)

    # Build controls from both legacy locations. A normalization key joins only exact normalized text.
    control_names: dict[str, str] = {}
    for stage in legacy_stages:
        for control in stage["controls"]:
            control_names.setdefault(norm(control), control)
    for family in families:
        for control in family["controls_targeted"]:
            control_names.setdefault(norm(control), control)
    control_ids = {key: f"CTL-{index:04d}" for index, key in enumerate(control_names, 1)}
    stage_control_ids: dict[str, set[str]] = defaultdict(set)
    for stage in stages:
        for control in stage["controls"]:
            stage_control_ids[control_ids[norm(control)]].add(stage["stage_id"])
    controls = [{"control_id": control_ids[key], "name": name,
                 "lifecycle_stage_ids": sorted(stage_control_ids[control_ids[key]]),
                 "detects_signal_ids": [], "evidence": []}
                for key, name in control_names.items()]
    write_json("controls.json", {"registry_version": "1.0", "controls": controls})

    evidence: list[dict[str, Any]] = []
    canonical_families: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    rel_index = 1
    for family in families:
        attack_id = family["attack_id"]
        source = source_for(attack_id)
        evidence_id = f"EVD-{attack_id}"
        confidence = family["evidence_confidence"] if family["evidence_confidence"] in {"VERIFIED", "SUPPORTED", "INFERRED", "UNVERIFIED"} else "UNVERIFIED"
        evidence.append({"evidence_id": evidence_id, "source": source or "legacy KB", "locator": None,
                         "excerpt": f"Taxonomy family {attack_id}; page/section locator was not retained by legacy extraction.",
                         "confidence": confidence, "maturity": None})
        stage_ids = stage_candidates(family["lifecycle_stage"], stages)
        classification_value, load_bearing, classification_note = classification(attack_id, source)
        signal_ids: list[str] = []
        for item in family["detection_signals"]:
            found = signal_aliases.get(norm(item["name"]))
            if found and found not in signal_ids:
                signal_ids.append(found)
        control_refs = [control_ids[norm(control)] for control in family["controls_targeted"]]
        record = {
            "attack_id": attack_id, "name": family["name"], "objective": None, "variants": family["variants"],
            "lifecycle_stage_id": stage_ids[0] if stage_ids else None, "cross_stage_lifecycle_stage_ids": [],
            "attacker": None, "target": None, "prerequisites": family["prerequisites"],
            "traditional_mechanism": None, "genai_transformation": None,
            "genai_classification": classification_value, "genai_load_bearing": load_bearing,
            "simulation_type": family["simulation_type"], "attack_flow": family["attack_flow"],
            "observable_signal_ids": signal_ids, "targeted_control_ids": control_refs,
            "evidence": [evidence_id], "confidence": confidence, "maturity": None,
        }
        canonical_families.append(record)
        for stage_id in stage_ids:
            relationships.append({"relationship_id": f"REL-{rel_index:05d}", "from_ref": attack_id,
                                  "relationship_type": "occurs_at", "to_ref": stage_id, "evidence": [evidence_id]}); rel_index += 1
        for signal_id in signal_ids:
            relationships.append({"relationship_id": f"REL-{rel_index:05d}", "from_ref": attack_id,
                                  "relationship_type": "observes", "to_ref": signal_id, "evidence": [evidence_id]}); rel_index += 1
        for control_id in control_refs:
            relationships.append({"relationship_id": f"REL-{rel_index:05d}", "from_ref": attack_id,
                                  "relationship_type": "targets", "to_ref": control_id, "evidence": [evidence_id]}); rel_index += 1
    write_json("attack_families.json", {"registry_version": "1.0", "attack_families": canonical_families})
    write_json("evidence.json", {"registry_version": "1.0", "evidence": evidence})
    write_json("relationships.json", {"registry_version": "1.0", "relationships": relationships})

    report = {
        "legacy_families": len(families), "canonical_families": len(canonical_families),
        "legacy_signals": len(signals), "canonical_signals": len(canonical_signals),
        "legacy_stages": len(legacy_stages), "canonical_stages": len(stages),
        "canonical_controls": len(controls), "evidence_records": len(evidence), "relationships": len(relationships),
        "unresolved_signal_aliases": sorted(set(unresolved_signal_aliases)),
        "unresolved_lifecycle_aliases": sorted(set(unresolved_stages)),
        "duplicate_global_signal_names": sorted(set(duplicate_signal_names)),
        "genai_classifications": dict(Counter(item["genai_classification"] for item in canonical_families)),
        "classification_notes": {item["attack_id"]: classification(item["attack_id"], source_for(item["attack_id"]))[2] for item in canonical_families},
    }
    write_json("normalization_metadata.json", report)


if __name__ == "__main__":
    main()
