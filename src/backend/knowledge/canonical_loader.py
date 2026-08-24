"""Read-only access to canonical knowledge registries.

This loader is intentionally separate from ``KnowledgeLoader`` so legacy Red
Team and API behavior stays unchanged during the migration.

Prefers the nested layout under ``data/knowledge/canonical/{attacks,defense,...}``.
Flat duplicate copies are no longer written.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


NESTED_FILES: Dict[str, Tuple[str, str]] = {
    "families": ("attacks/attack_families.json", "attack_families"),
    "variants": ("attacks/attack_variants.json", "attack_variants"),
    "vectors": ("attacks/attack_vectors.json", "attack_vectors"),
    "relationships": ("attacks/attack_relationships.json", "relationships"),
    "signals": ("defense/signals.json", "signals"),
    "controls": ("defense/controls.json", "controls"),
    "mappings": ("defense/signal_feature_mappings.json", "signal_feature_mappings"),
    "stages": ("lifecycle/lifecycle_stages.json", "lifecycle_stages"),
    "templates": ("simulation/simulation_templates.json", "simulation_templates"),
    "parameters": ("simulation/parameters.json", "parameters"),
    "requirements": ("simulation/state_requirements.json", "state_requirements"),
    "counterparts": ("simulation/legitimate_counterparts.json", "legitimate_counterparts"),
    "capabilities": ("genai/capabilities.json", "capabilities"),
    "evidence": ("evidence/evidence.json", "evidence"),
}

FLAT_FILES: Dict[str, Tuple[str, str]] = {
    "families": ("attack_families.json", "attack_families"),
    "variants": ("attack_variants.json", "attack_variants"),
    "vectors": ("attack_vectors.json", "attack_vectors"),
    "relationships": ("relationships.json", "relationships"),
    "signals": ("signals.json", "signals"),
    "controls": ("controls.json", "controls"),
    "mappings": ("signal_feature_mappings.json", "signal_feature_mappings"),
    "stages": ("lifecycle_stages.json", "lifecycle_stages"),
    "templates": ("simulation_templates.json", "simulation_templates"),
    "parameters": ("simulation_parameters.json", "parameters"),
    "requirements": ("state_requirements.json", "state_requirements"),
    "counterparts": ("legitimate_counterparts.json", "legitimate_counterparts"),
    "capabilities": ("genai_capabilities.json", "capabilities"),
    "evidence": ("evidence.json", "evidence"),
}


class CanonicalKnowledgeLoader:
    def __init__(self, kb_path: Optional[str] = None):
        self.kb_path = Path(kb_path) if kb_path else Path("data/knowledge/canonical")
        self.families = self._load("families")
        self.variants = self._load("variants")
        self.vectors = self._load("vectors")
        self.relationships = self._load("relationships")
        self.signals = self._load("signals")
        self.stages = self._load("stages")
        self.controls = self._load("controls")
        self.mappings = self._load("mappings")
        self.templates = self._load("templates")
        self.parameters = self._load("parameters")
        self.requirements = self._load("requirements")
        self.counterparts = self._load("counterparts")
        self.capabilities = self._load("capabilities")
        self.evidence = self._load("evidence")

    def _load(self, name: str) -> List[Dict[str, Any]]:
        nested_file, nested_key = NESTED_FILES[name]
        nested_path = self.kb_path / nested_file
        if nested_path.exists():
            return self._read(nested_path, nested_key)
        flat_file, flat_key = FLAT_FILES[name]
        flat_path = self.kb_path / flat_file
        if flat_path.exists():
            return self._read(flat_path, flat_key)
        return []

    @staticmethod
    def _read(path: Path, key: str) -> List[Dict[str, Any]]:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle).get(key, [])

    @staticmethod
    def _find(records: List[Dict[str, Any]], key: str, value: str) -> Optional[Dict[str, Any]]:
        return next((record for record in records if record.get(key) == value), None)

    def get_family(self, attack_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.families, "attack_id", attack_id)

    def get_variant(self, variant_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.variants, "variant_id", variant_id)

    def get_vector(self, vector_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.vectors, "vector_id", vector_id)

    def get_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.signals, "signal_id", signal_id)

    def get_stage(self, stage_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.stages, "stage_id", stage_id)

    def get_control(self, control_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.controls, "control_id", control_id)

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.templates, "template_id", template_id)

    def get_capability(self, capability_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.capabilities, "capability_id", capability_id)

    def get_family_signals(self, attack_id: str) -> List[Dict[str, Any]]:
        family = self.get_family(attack_id) or {}
        return [item for identifier in family.get("observable_signal_ids", []) if (item := self.get_signal(identifier))]

    def get_family_controls(self, attack_id: str) -> List[Dict[str, Any]]:
        family = self.get_family(attack_id) or {}
        return [item for identifier in family.get("targeted_control_ids", []) if (item := self.get_control(identifier))]

    def get_family_stages(self, attack_id: str) -> List[Dict[str, Any]]:
        family = self.get_family(attack_id) or {}
        identifiers = [family.get("lifecycle_stage_id"), *family.get("cross_stage_lifecycle_stage_ids", [])]
        return [item for identifier in identifiers if identifier and (item := self.get_stage(identifier))]

    def get_family_variants(self, attack_id: str) -> List[Dict[str, Any]]:
        return [item for item in self.variants if item.get("family_id") == attack_id]

    def get_family_vectors(self, attack_id: str) -> List[Dict[str, Any]]:
        return [item for item in self.vectors if item.get("family_id") == attack_id]

    def get_signal_features(self, signal_id: str) -> List[str]:
        names: List[str] = []
        for mapping in self.mappings:
            if mapping.get("signal_id") == signal_id:
                names.extend(mapping.get("feature_names") or [])
        return names

    def catalog_stats(self) -> Dict[str, int]:
        return {
            "families": len(self.families),
            "variants": len(self.variants),
            "vectors": len(self.vectors),
            "signals": len(self.signals),
            "controls": len(self.controls),
            "stages": len(self.stages),
            "relationships": len(self.relationships),
            "templates": len(self.templates),
            "parameters": len(self.parameters),
            "capabilities": len(self.capabilities),
            "mappings": len(self.mappings),
            "counterparts": len(self.counterparts),
            "evidence": len(self.evidence),
        }

    def to_legacy_family(self, attack_id: str) -> Optional[Dict[str, Any]]:
        """Project a canonical family into the legacy runtime shape.

        Used later as a compatibility adapter. Does not replace KnowledgeLoader.
        """
        family = self.get_family(attack_id)
        if not family:
            return None
        stage = self.get_stage(family.get("lifecycle_stage_id") or "")
        signals = self.get_family_signals(attack_id)
        controls = self.get_family_controls(attack_id)
        genai = family.get("genai") or {}
        classification = genai.get("classification") or family.get("genai_classification")
        legacy_genai = "PASS" if classification == "genai_load_bearing" else "PARTIAL"
        return {
            "attack_id": family.get("attack_id"),
            "name": family.get("name"),
            "variants": family.get("variants") or [item.get("name") for item in self.get_family_variants(attack_id)],
            "lifecycle_stage": (stage or {}).get("name"),
            "genai_classification": legacy_genai,
            "simulation_type": family.get("simulation_type"),
            "prerequisites": family.get("prerequisites") or [],
            "attack_flow": family.get("attack_flow") or [],
            "detection_signals": [
                {"name": item.get("name"), "detection_method": "; ".join(item.get("detection_methods") or [])}
                for item in signals
            ],
            "controls_targeted": [item.get("name") for item in controls if item.get("name")],
            "evidence_confidence": family.get("confidence"),
        }
