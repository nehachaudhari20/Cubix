"""
Base Rule Class with KB API + executable control registry integration.
"""

import os
import time
from typing import Any, Dict, List

import requests

from .control_registry import get_registry_defaults, merge_kb_control_names

KB_API_URL = os.environ.get("KB_API_URL", "http://localhost:8000")
USE_KB_API = os.environ.get("USE_KB_API", "false").lower() in ("1", "true", "yes")


class BaseRule:
    """Base class for sandbox rules with KB-aware executable controls."""

    def __init__(self, stage: str):
        self.stage = stage
        self._controls_cache: Dict[str, Any] | None = None
        self._cache_ttl = 60
        self._cache_time = 0.0

    def get_controls(self) -> Dict[str, Any]:
        """Fetch merged executable controls (registry defaults + optional KB names)."""
        registry_defaults = get_registry_defaults(self.stage)
        subclass_defaults = self._get_default_controls()
        defaults = {**registry_defaults, **subclass_defaults}

        if not USE_KB_API:
            return defaults

        current_time = time.time()
        if self._controls_cache and (current_time - self._cache_time) < self._cache_ttl:
            return self._controls_cache

        try:
            from urllib.parse import quote
            url = f"{KB_API_URL}/stages/{quote(self.stage, safe='')}/controls"
            response = requests.get(url, timeout=(0.3, 0.5))

            if response.status_code == 200:
                data = response.json()
                kb_controls = data.get("controls", [])
                if isinstance(kb_controls, dict):
                    kb_controls = list(kb_controls.values())
                merged = merge_kb_control_names(defaults, kb_controls if isinstance(kb_controls, list) else [])
                self._controls_cache = merged
                self._cache_time = current_time
                return merged
        except requests.exceptions.RequestException:
            pass

        return defaults

    def _get_default_controls(self) -> Dict[str, Any]:
        """Rule-specific defaults (override registry when needed)."""
        return {}

    def get_control_value(self, control_name: str, default: Any) -> Any:
        """Get a numeric or boolean control value."""
        controls = self.get_controls()
        key = control_name.lower().replace(" ", "_")
        value = controls.get(key, default)
        if isinstance(value, (int, float, bool)):
            return value
        return default

    def has_kb_control(self, *keywords: str) -> bool:
        """Check if KB listed a control matching any keyword (when USE_KB_API=true)."""
        if not USE_KB_API:
            return False
        names: List[str] = self.get_controls().get("_kb_control_names", [])
        for name in names:
            for kw in keywords:
                if kw.lower().replace(" ", "_") in name:
                    return True
        return False

    def kb_controls_list(self) -> List[str]:
        """Return KB control names attached to this stage."""
        return self.get_controls().get("_kb_control_names", [])
