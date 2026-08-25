"""Compile canonical KB control metadata + executable thresholds at sandbox boot."""

from __future__ import annotations

import fnmatch
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader

from .compiled_controls import CompiledControlSet
from .control_implementations import build_trigger_map
from .control_registry import EXECUTABLE_DEFAULTS


_REF_PATTERN = re.compile(
    r"^EXECUTABLE_DEFAULTS\.(?P<registry>[a-z_]+)(?:\.(?P<param>[a-z0-9_*]+))?$",
    re.IGNORECASE,
)


class ControlCompiler:
    """Build a CompiledControlSet from canonical KB + EXECUTABLE_DEFAULTS."""

    def __init__(self, kb_path: str = "data/knowledge/canonical"):
        self.loader = CanonicalKnowledgeLoader(kb_path)

    def compile(self) -> CompiledControlSet:
        thresholds = {key: dict(values) for key, values in EXECUTABLE_DEFAULTS.items()}
        controls_by_id = {
            item["control_id"]: item
            for item in self.loader.controls
            if item.get("control_id")
        }
        stage_id_to_control_ids: Dict[str, List[str]] = {}
        for control in self.loader.controls:
            control_id = control.get("control_id")
            if not control_id:
                continue
            for stage_id in control.get("lifecycle_stage_ids") or []:
                stage_id_to_control_ids.setdefault(stage_id, []).append(control_id)

        parameter_bindings = self._resolve_parameter_bindings(thresholds)
        errors = self.validate_refs(parameter_bindings)
        if errors:
            raise ValueError(f"ControlCompiler validation failed: {errors[:5]}")

        return CompiledControlSet(
            thresholds=thresholds,
            controls_by_id=controls_by_id,
            stage_id_to_control_ids=stage_id_to_control_ids,
            parameter_bindings=parameter_bindings,
            trigger_to_control_id=build_trigger_map(),
            compiled_at=datetime.now(timezone.utc).isoformat(),
        )

    def _resolve_parameter_bindings(
        self, thresholds: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        bindings: Dict[str, Dict[str, Any]] = {}
        for parameter in self.loader.parameters:
            parameter_id = parameter.get("parameter_id")
            if not parameter_id:
                continue
            ref = parameter.get("sandbox_config_ref")
            bindings[parameter_id] = {
                "parameter_id": parameter_id,
                "name": parameter.get("name"),
                "sandbox_config_ref": ref,
                "resolved": self._resolve_ref(ref, thresholds) if ref else {},
            }
        return bindings

    def _resolve_ref(
        self, ref: str, thresholds: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        match = _REF_PATTERN.match(ref.strip())
        if not match:
            return {}
        registry_key = match.group("registry")
        param = match.group("param")
        registry_values = thresholds.get(registry_key, {})
        if not param:
            return dict(registry_values)
        if "*" in param:
            prefix = param.replace("*", "")
            return {
                key: value
                for key, value in registry_values.items()
                if fnmatch.fnmatch(key, param) or key.startswith(prefix)
            }
        if param in registry_values:
            return {param: registry_values[param]}
        return {}

    def validate_refs(
        self, parameter_bindings: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[str]:
        errors: List[str] = []
        bindings = parameter_bindings or self._resolve_parameter_bindings(
            {key: dict(values) for key, values in EXECUTABLE_DEFAULTS.items()}
        )
        for parameter_id, binding in bindings.items():
            ref = binding.get("sandbox_config_ref")
            if not ref:
                continue
            match = _REF_PATTERN.match(ref.strip())
            if not match:
                errors.append(f"{parameter_id}: malformed sandbox_config_ref {ref!r}")
                continue
            registry_key = match.group("registry")
            if registry_key not in EXECUTABLE_DEFAULTS:
                errors.append(f"{parameter_id}: unknown registry key {registry_key!r}")
                continue
            param = match.group("param")
            if param and "*" not in param and param not in EXECUTABLE_DEFAULTS[registry_key]:
                errors.append(f"{parameter_id}: unknown parameter {param!r} in {registry_key}")
        return errors

    @staticmethod
    def get_threshold_for_parameter(
        compiled: CompiledControlSet, parameter_id: str, key: str, default: Any
    ) -> Any:
        binding = compiled.parameter_bindings.get(parameter_id, {})
        resolved = binding.get("resolved") or {}
        if key in resolved:
            return resolved[key]
        if len(resolved) == 1:
            return next(iter(resolved.values()))
        return default
