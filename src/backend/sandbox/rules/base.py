"""
Base Rule Class — uses CompiledControlSet at boot (no runtime KB access).
"""

from typing import Any, Dict, List, Optional

from .compiled_controls import CompiledControlSet, get_global_compiled_controls
from .control_registry import get_registry_defaults


class BaseRule:
    """Base class for sandbox rules with boot-time compiled controls."""

    def __init__(self, stage: str, compiled_controls: Optional[CompiledControlSet] = None):
        self.stage = stage
        self._compiled = compiled_controls

    @property
    def compiled(self) -> Optional[CompiledControlSet]:
        return self._compiled or get_global_compiled_controls()

    def get_controls(self) -> Dict[str, Any]:
        """Return executable controls from the compiled set (no HTTP/KB at runtime)."""
        compiled = self.compiled
        if compiled is not None:
            defaults = compiled.get_stage_defaults(self.stage)
        else:
            defaults = get_registry_defaults(self.stage)
        subclass_defaults = self._get_default_controls()
        return {**defaults, **subclass_defaults}

    def _get_default_controls(self) -> Dict[str, Any]:
        return {}

    def get_control_value(self, control_name: str, default: Any) -> Any:
        controls = self.get_controls()
        key = control_name.lower().replace(" ", "_")
        value = controls.get(key, default)
        if isinstance(value, (int, float, bool)):
            return value
        return default

    def has_kb_control(self, *keywords: str) -> bool:
        names: List[str] = self.get_controls().get("_kb_control_names", [])
        for name in names:
            for kw in keywords:
                if kw.lower().replace(" ", "_") in name:
                    return True
        return False

    def kb_controls_list(self) -> List[str]:
        return self.get_controls().get("_kb_control_names", [])
