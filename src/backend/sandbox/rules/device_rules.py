"""Device-Based Static Rules with KB API Integration"""

from typing import Dict, Any
from .base import BaseRule


class DeviceRules(BaseRule):
    """Rules based on device characteristics."""
    
    def __init__(self):
        super().__init__("Device_Session")
    
    def _get_default_controls(self) -> Dict[str, Any]:
        return {
            "new_device_risk": 0.20,
            "device_age_threshold": 30,
            "device_age_risk": 0.10,
            "unknown_device_risk": 0.30
        }
    
    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate device-based rules using KB controls."""
        risk_contribution = 0.0
        triggered_rules = []
        
        is_new_device = features.get("is_new_device", True)
        device_age_days = features.get("device_age_days", 0)
        
        # Fetch controls from KB API
        new_device_risk = self.get_control_value("new_device_risk", 0.20)
        age_threshold = self.get_control_value("device_age_threshold", 30)
        age_risk = self.get_control_value("device_age_risk", 0.10)
        unknown_risk = self.get_control_value("unknown_device_risk", 0.30)
        
        # Unknown device (device not found in registry)
        is_unknown = features.get("is_unknown_device", False)
        if is_unknown:
            risk_contribution += unknown_risk
            triggered_rules.append("unknown_device")

        # New device (registered but less than 7 days old)
        elif is_new_device:
            risk_contribution += new_device_risk
            triggered_rules.append("new_device_less_than_7_days")
        
        # Device age less than threshold
        if device_age_days < age_threshold and not is_new_device:
            risk_contribution += age_risk
            triggered_rules.append(f"device_age_less_than_{age_threshold}_days")
        
        return {
            "rule_set": "device_rules",
            "risk_contribution": min(0.4, risk_contribution),
            "triggered_rules": triggered_rules,
            "is_new_device": is_new_device,
            "device_age_days": device_age_days,
            "thresholds_applied": {"new_device_risk": new_device_risk, "age_threshold": age_threshold}
        }