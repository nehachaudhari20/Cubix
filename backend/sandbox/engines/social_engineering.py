"""
Social Engineering Engine — STG-0004 (Authentication).

Adjudicates the `auth_se` surface: phishing, smishing, BEC, vishing, OTP
coercion, and authentication-recovery exploitation.

The victim is modelled as state, not as a coin flip: a customer who disclosed an
OTP an hour ago is a softer target now, and repeated attempts against the same
customer within the window raise the surface's own risk.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from ..state import AuthEvent, SandboxState


# Channels where the bank has weaker provenance guarantees
LOW_ASSURANCE_CHANNELS = ("voice", "sms", "email")


class SocialEngineeringEngine:
    """Channel provenance, victim susceptibility, and OTP disclosure checks."""

    def __init__(self, state: SandboxState):
        self.state = state

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        customer_id = payload.get("customer_id") or ""
        channel = str(payload.get("channel") or "web").lower()
        method = str(payload.get("authentication_method") or "otp").lower()
        genai = payload.get("genai_features") or {}
        customer = self.state.get_customer(customer_id)

        se_score = float(genai.get("social_engineering_score") or 0)
        phishing = float(genai.get("phishing_content_risk") or 0)
        vishing = float(genai.get("vishing_risk") or 0)
        voice_clone = float(genai.get("voice_cloning_score") or 0)
        bec = float(genai.get("bec_content_risk") or 0)

        # --- channel provenance -------------------------------------------------
        if channel in LOW_ASSURANCE_CHANNELS:
            flags.append("se_low_assurance_channel")
        if channel == "voice" and (voice_clone >= 0.55 or vishing >= 0.55):
            flags.append("se_synthetic_voice_detected")
        if channel in ("email", "sms") and max(phishing, bec) >= 0.60:
            flags.append("se_phishing_content_detected")
        if float(genai.get("channel_spoof_risk") or 0) >= 0.55:
            flags.append("se_channel_spoofed")

        # --- victim susceptibility (state-driven) --------------------------------
        prior = self.state.get_auth_events(customer_id, hours=24)
        prior_coerced = [e for e in prior if e.victim_coerced]
        prior_disclosed = [e for e in prior if e.otp_disclosed]
        if len(prior) >= 3:
            flags.append("se_repeated_auth_attempts_24h")
        if prior_disclosed:
            flags.append("se_prior_otp_disclosure")

        base_resistance = float(customer.trust_score) if customer else 0.5
        # Each prior successful coercion lowers resistance for this attempt.
        resistance = max(0.0, base_resistance - 0.15 * len(prior_coerced))
        pressure = max(se_score, vishing, phishing, bec)
        coerced = bool(payload.get("victim_coerced")) or pressure > resistance

        # --- OTP disclosure ------------------------------------------------------
        otp_disclosed = False
        if method in ("otp", "sms_otp") and coerced:
            otp_disclosed = True
            flags.append("se_otp_disclosed_to_third_party")

        # --- recovery flow -------------------------------------------------------
        if payload.get("recovery_flow"):
            flags.append("se_recovery_flow_invoked")
            if float(genai.get("recovery_fraud_risk") or 0) >= 0.55:
                flags.append("se_recovery_fraud_indicators")

        succeeded = coerced and not (
            "se_synthetic_voice_detected" in flags and channel == "voice" and method == "voice_verification"
        )

        self.state.add_auth_event(
            AuthEvent(
                event_id=f"auth_{uuid.uuid4().hex[:8]}",
                customer_id=customer_id,
                channel=channel,
                method=method,
                created_at=datetime.now(),
                succeeded=succeeded,
                otp_disclosed=otp_disclosed,
                victim_coerced=coerced,
            )
        )

        risk = min(1.0, 0.16 * len(flags) + pressure * 0.25)
        return {
            "status": "PASS",
            "stage": "STG-0004",
            "engine": "auth_se",
            "flags": flags,
            "auth_se_risk": round(risk, 4),
            "channel": channel,
            "victim_coerced": coerced,
            "otp_disclosed": otp_disclosed,
            "victim_resistance": round(resistance, 4),
            "social_pressure": round(pressure, 4),
            "prior_attempts_24h": len(prior),
            "se_credential_compromised": succeeded,
        }
