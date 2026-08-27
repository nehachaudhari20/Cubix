"""
Session Integrity Engine — STG-0028 (Device / Session).

Adjudicates the `device` surface: on-device remote access (RAT), automated bot
interaction at machine speed, and GAN-generated behavioural-biometric evasion.

These are the families a payment-only sandbox cannot express at all: the attack
happens inside the session, before any transaction exists.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..state import SandboxState


class SessionIntegrityEngine:
    """Remote-control, automation, and behavioural-biometric checks."""

    def __init__(self, state: SandboxState):
        self.state = state

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        customer_id = payload.get("customer_id") or ""
        device_id = payload.get("device_id")
        genai = payload.get("genai_features") or {}
        device = self.state.get_device(device_id) if device_id else None

        # --- remote access / overlay ---------------------------------------------
        if payload.get("remote_access_active"):
            flags.append("dev_remote_access_detected")
        if payload.get("accessibility_service_active"):
            flags.append("dev_accessibility_abuse")
        if payload.get("screen_overlay_active"):
            flags.append("dev_screen_overlay_detected")

        # --- automation ----------------------------------------------------------
        interaction_ms = payload.get("mean_interaction_interval_ms")
        if interaction_ms is not None and float(interaction_ms) < 80:
            flags.append("dev_machine_speed_interaction")
        if float(genai.get("scale_automation_score") or 0) >= 0.60:
            flags.append("dev_automation_indicators")
        if payload.get("headless_client"):
            flags.append("dev_headless_client")

        # --- behavioural biometrics ---------------------------------------------
        behavioural_variance = payload.get("behavioural_variance")
        if behavioural_variance is not None and float(behavioural_variance) < 0.10:
            # Real humans are noisy; near-zero variance implies synthesis.
            flags.append("dev_behavioural_variance_too_low")
        if float(genai.get("behavioral_camouflage_score") or 0) >= 0.60:
            flags.append("dev_behavioural_camouflage")
        if float(genai.get("biometric_synthesis_score") or 0) >= 0.60:
            flags.append("dev_synthetic_biometric_telemetry")

        # --- device provenance (state-driven) ------------------------------------
        if device is None:
            flags.append("dev_unknown_device")
        elif device.get_age_days() < 7:
            flags.append("dev_new_device_session")

        recent_sessions = self.state.count_surface_events(customer_id, "device", hours=1)
        if recent_sessions >= 5:
            flags.append("dev_session_churn")

        risk = min(1.0, 0.17 * len(flags))
        return {
            "status": "PASS",
            "stage": "STG-0028",
            "engine": "session_integrity",
            "flags": flags,
            "session_risk": round(risk, 4),
            "device_id": device_id,
            "device_known": device is not None,
            "recent_sessions_1h": recent_sessions,
            "session_compromised": bool(
                {"dev_remote_access_detected", "dev_accessibility_abuse"} & set(flags)
            ),
        }
