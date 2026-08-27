"""Runtime knowledge loader.

Reads the canonical nested KB under ``data/knowledge/canonical/`` and applies
in-memory compatibility aliases (``lifecycle_stage``, ``detection_signals``,
``controls_targeted``, etc.) so Red Team and the API keep working without
duplicate JSON files at ``data/knowledge/``.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .canonical_loader import CanonicalKnowledgeLoader


class KnowledgeLoader:
    def __init__(self, kb_path: str = "data/knowledge/"):
        canonical_path = os.path.join(kb_path, "canonical")
        if not os.path.isdir(canonical_path):
            canonical_path = "data/knowledge/canonical"
        self.canonical = CanonicalKnowledgeLoader(canonical_path)
        raw_controls = self.canonical.controls
        self.signals = [self._hydrate_signal(item) for item in self.canonical.signals]
        self.stages = [self._hydrate_stage(item) for item in self.canonical.stages]
        self.families = self._hydrate_families(
            self.canonical.families,
            self.canonical.signals,
            self.canonical.stages,
            raw_controls,
        )

    @staticmethod
    def _hydrate_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
        record = dict(signal)
        record.setdefault("name", record.get("signal_name") or "")
        record.setdefault("signal_name", record.get("name") or "")
        methods = record.get("detection_methods")
        if isinstance(methods, list):
            record.setdefault("detection_method", "; ".join(methods))
        elif record.get("detection_method") and "detection_methods" not in record:
            record["detection_methods"] = [
                part.strip() for part in str(record["detection_method"]).split(";") if part.strip()
            ]
        return record

    @staticmethod
    def _hydrate_stage(stage: Dict[str, Any]) -> Dict[str, Any]:
        record = dict(stage)
        name = record.get("name") or record.get("stage_name") or record.get("stage") or ""
        record["name"] = name
        record["stage_name"] = name
        record["stage"] = name
        record.setdefault("controls", [])
        return record

    def _hydrate_families(
        self,
        families: List[Dict[str, Any]],
        signals: List[Dict[str, Any]],
        stages: List[Dict[str, Any]],
        controls: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        signal_by_id = {item.get("signal_id"): self._hydrate_signal(item) for item in signals if item.get("signal_id")}
        stage_by_id = {item.get("stage_id"): self._hydrate_stage(item) for item in stages if item.get("stage_id")}
        control_by_id = {item.get("control_id"): item for item in controls if item.get("control_id")}
        hydrated: List[Dict[str, Any]] = []
        for family in families:
            record = dict(family)
            stage = stage_by_id.get(record.get("lifecycle_stage_id") or "")
            record["lifecycle_stage"] = (stage or {}).get("name") or record.get("lifecycle_stage") or ""
            record["detection_signals"] = [
                {
                    "signal_id": signal_id,
                    "name": (signal_by_id.get(signal_id) or {}).get("name"),
                    "detection_method": (signal_by_id.get(signal_id) or {}).get("detection_method") or "",
                }
                for signal_id in record.get("observable_signal_ids") or []
                if signal_id in signal_by_id
            ]
            record["controls_targeted"] = [
                (control_by_id.get(control_id) or {}).get("name")
                for control_id in record.get("targeted_control_ids") or []
                if control_id in control_by_id and (control_by_id.get(control_id) or {}).get("name")
            ]
            record["evidence_confidence"] = record.get("confidence") or "UNVERIFIED"
            record.setdefault("variants", [])
            hydrated.append(record)
        return hydrated

    def get_family(self, family_id: str) -> Optional[Dict[str, Any]]:
        return next((item for item in self.families if item.get("attack_id") == family_id), None)

    def get_families_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        target = (stage or "").strip().casefold()
        return [
            item for item in self.families
            if target in {
                (item.get("lifecycle_stage") or "").casefold(),
                (item.get("lifecycle_stage_id") or "").casefold(),
            }
        ]

    def get_signals_by_family(self, family_id: str) -> List[Dict[str, Any]]:
        family = self.get_family(family_id)
        if not family:
            return []
        return family.get("detection_signals") or []

    def get_all_controls(self) -> Dict[str, List[str]]:
        controls: Dict[str, List[str]] = {}
        for stage in self.stages:
            name = stage.get("stage") or stage.get("stage_name") or stage.get("name") or "Unknown"
            controls[name] = stage.get("controls") or []
        return controls
