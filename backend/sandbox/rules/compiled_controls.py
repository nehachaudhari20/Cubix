"""Immutable compiled control set produced at sandbox boot from canonical KB."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_compiled_instance: Optional["CompiledControlSet"] = None


@dataclass(frozen=True)
class CompiledControlSet:
    """Executable controls + KB metadata, compiled once at boot."""

    thresholds: Dict[str, Dict[str, Any]]
    controls_by_id: Dict[str, Dict[str, Any]]
    stage_id_to_control_ids: Dict[str, List[str]]
    parameter_bindings: Dict[str, Dict[str, Any]]
    trigger_to_control_id: Dict[str, str]
    compiled_at: str
    source: str = "data/knowledge/canonical/"

    def get_stage_defaults(self, stage: str) -> Dict[str, Any]:
        from .control_registry import resolve_registry_key

        key = resolve_registry_key(stage)
        if key and key in self.thresholds:
            return dict(self.thresholds[key])
        return {}

    def get_control(self, control_id: str) -> Optional[Dict[str, Any]]:
        return self.controls_by_id.get(control_id)

    def resolve_trigger(self, internal_trigger: str) -> Optional[str]:
        if not internal_trigger:
            return None
        if internal_trigger.startswith("CTL-"):
            return internal_trigger
        if internal_trigger in self.trigger_to_control_id:
            return self.trigger_to_control_id[internal_trigger]
        for prefix, control_id in self.trigger_to_control_id.items():
            if prefix.endswith("*") and internal_trigger.startswith(prefix[:-1]):
                return control_id
            if internal_trigger.startswith(prefix):
                return control_id
        return None

    def resolve_triggers(self, internal_triggers: List[str]) -> List[str]:
        """Map internal rule triggers to KB control IDs; keep unmapped as-is."""
        resolved: List[str] = []
        seen: set[str] = set()
        for trigger in internal_triggers:
            control_id = self.resolve_trigger(trigger) or trigger
            if control_id not in seen:
                seen.add(control_id)
                resolved.append(control_id)
        return resolved

    def stats(self) -> Dict[str, Any]:
        return {
            "registry_keys": len(self.thresholds),
            "controls": len(self.controls_by_id),
            "parameter_bindings": len(self.parameter_bindings),
            "trigger_mappings": len(self.trigger_to_control_id),
            "source": self.source,
            "compiled_at": self.compiled_at,
        }


def set_global_compiled_controls(compiled: CompiledControlSet) -> None:
    global _compiled_instance
    _compiled_instance = compiled


def get_global_compiled_controls() -> Optional[CompiledControlSet]:
    return _compiled_instance


def clear_global_compiled_controls() -> None:
    global _compiled_instance
    _compiled_instance = None
