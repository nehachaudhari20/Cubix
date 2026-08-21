"""Device-Based Static Rules"""

from typing import Dict, Any


class DeviceRules:
    """Rules based on device characteristics."""
    
    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate device-based rules."""
        risk_contribution = 0.0
        triggered_rules = []
        
        is_new_device = features.get("is_new_device", True)
        device_age_days = features.get("device_age_days", 0)
        
        # New device rule
        if is_new_device:
            risk_contribution += 0.2
            triggered_rules.append("new_device")
        
        # Device age < 30 days
        if device_age_days < 30 and not is_new_device:
            risk_contribution += 0.1
            triggered_rules.append("device_age_less_than_30_days")
        
        return {
            "rule_set": "device_rules",
            "risk_contribution": min(0.3, risk_contribution),
            "triggered_rules": triggered_rules,
            "is_new_device": is_new_device,
            "device_age_days": device_age_days
        }