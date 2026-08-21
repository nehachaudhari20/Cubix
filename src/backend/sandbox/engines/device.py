"""Device Fingerprinting Engine"""

from typing import Dict, Any
from ..state import SandboxState


class DeviceEngine:
    """Device fingerprinting and risk engine."""
    
    def __init__(self, state: SandboxState):
        self.state = state
    
    def check_device(self, device_id: str, customer_id: str) -> Dict[str, Any]:
        """Check if a device is legitimate."""
        device = self.state.get_device(device_id)
        
        if not device:
            return {
                "status": "FLAG",
                "reason": "unknown_device",
                "message": "Device not registered",
                "is_new": True,
                "device_age_days": 0
            }
        
        if device.customer_id != customer_id:
            return {
                "status": "FLAG",
                "reason": "device_customer_mismatch",
                "message": "Device belongs to different customer",
                "is_new": False,
                "device_age_days": device.get_age_days()
            }
        
        age_days = device.get_age_days()
        is_new = age_days < 7
        
        return {
            "status": "PASS",
            "device_id": device_id,
            "device_age_days": age_days,
            "is_new": is_new,
            "customer_id": device.customer_id
        }