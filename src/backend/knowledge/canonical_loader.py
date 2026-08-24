"""Read-only access to canonical knowledge registries.

This loader is intentionally separate from ``KnowledgeLoader`` so legacy Red
Team and API behavior stays unchanged during the migration.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class CanonicalKnowledgeLoader:
    def __init__(self, kb_path: Optional[str] = None):
        self.kb_path = Path(kb_path) if kb_path else Path("data/knowledge/canonical")
        self.families = self._load("attack_families.json", "attack_families")
        self.signals = self._load("signals.json", "signals")
        self.stages = self._load("lifecycle_stages.json", "lifecycle_stages")
        self.controls = self._load("controls.json", "controls")

    def _load(self, filename: str, key: str) -> List[Dict[str, Any]]:
        with (self.kb_path / filename).open(encoding="utf-8") as handle:
            return json.load(handle).get(key, [])

    @staticmethod
    def _find(records: List[Dict[str, Any]], key: str, value: str) -> Optional[Dict[str, Any]]:
        return next((record for record in records if record.get(key) == value), None)

    def get_family(self, attack_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.families, "attack_id", attack_id)

    def get_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.signals, "signal_id", signal_id)

    def get_stage(self, stage_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.stages, "stage_id", stage_id)

    def get_control(self, control_id: str) -> Optional[Dict[str, Any]]:
        return self._find(self.controls, "control_id", control_id)

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
