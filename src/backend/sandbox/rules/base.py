"""
Base Rule Class with KB API Integration
All rules inherit from this to dynamically fetch controls.
"""

import requests
import os
from typing import Dict, Any, Optional

# KB API URL (from environment or default)
KB_API_URL = os.environ.get("KB_API_URL", "http://localhost:8000")


class BaseRule:
    """Base class for all static rules with KB API integration."""
    
    def __init__(self, stage: str):
        self.stage = stage
        self._controls_cache = None
        self._cache_ttl = 60  # Cache for 60 seconds
        self._cache_time = 0
    
    def get_controls(self) -> Dict[str, Any]:
        """Fetch controls for this stage from KB API."""
        import time
        
        # Check cache
        current_time = time.time()
        if self._controls_cache and (current_time - self._cache_time) < self._cache_ttl:
            return self._controls_cache
        
        try:
            url = f"{KB_API_URL}/stages/{self.stage}/controls"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                controls = data.get("controls", {})
                
                # Convert list to dict for easier lookup
                controls_dict = {}
                for control in controls:
                    if isinstance(control, str):
                        controls_dict[control.lower().replace(" ", "_")] = control
                    else:
                        # If control is an object, handle accordingly
                        pass
                
                self._controls_cache = controls_dict
                self._cache_time = current_time
                return controls_dict
            else:
                # Fallback to default controls
                return self._get_default_controls()
                
        except requests.exceptions.RequestException:
            # If API is down, use default controls
            return self._get_default_controls()
    
    def _get_default_controls(self) -> Dict[str, Any]:
        """Fallback default controls if KB API is unavailable."""
        # Subclasses should override this
        return {}
    
    def get_control_value(self, control_name: str, default: Any) -> Any:
        """Get a specific control value by name."""
        controls = self.get_controls()
        return controls.get(control_name.lower().replace(" ", "_"), default)