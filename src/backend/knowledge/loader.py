"""Runtime knowledge loader.

Loads the published KB at data/knowledge/{attack_families,attack_signals,lifecycle_stages}.json.
Those files are the canonical registries plus compatibility aliases so Red Team
and the API keep working while using the final data model.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


class KnowledgeLoader:
    def __init__(self, kb_path: str = "data/knowledge/"):
        self.kb_path = kb_path
        self.families = self._hydrate_families(
            self._load("attack_families.json", "attack_families"),
            self._load("attack_signals.json", "signals"),
            self._load("lifecycle_stages.json", "lifecycle_stages"),
        )
        self.signals = [self._hydrate_signal(item) for item in self._load("attack_signals.json", "signals")]
        self.stages = [self._hydrate_stage(item) for item in self._load("lifecycle_stages.json", "lifecycle_stages")]

    def _load(self, filename: str, key: str) -> List[Dict[str, Any]]:
        path = os.path.join(self.kb_path, filename)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
            return data.get(key, [])

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
    ) -> List[Dict[str, Any]]:
        signal_by_id = {item.get("signal_id"): self._hydrate_signal(item) for item in signals if item.get("signal_id")}
        stage_by_id = {item.get("stage_id"): self._hydrate_stage(item) for item in stages if item.get("stage_id")}
        hydrated: List[Dict[str, Any]] = []
        for family in families:
            record = dict(family)
            stage = stage_by_id.get(record.get("lifecycle_stage_id") or "")
            if not record.get("lifecycle_stage"):
                record["lifecycle_stage"] = (stage or {}).get("name") or ""
            if not record.get("detection_signals"):
                record["detection_signals"] = [
                    {
                        "signal_id": signal_id,
                        "name": (signal_by_id.get(signal_id) or {}).get("name"),
                        "detection_method": (signal_by_id.get(signal_id) or {}).get("detection_method") or "",
                    }
                    for signal_id in record.get("observable_signal_ids") or []
                    if signal_id in signal_by_id
                ]
            if not record.get("controls_targeted"):
                record["controls_targeted"] = list(record.get("targeted_control_names") or [])
            record.setdefault("evidence_confidence", record.get("confidence"))
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
