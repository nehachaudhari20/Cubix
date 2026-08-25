"""
GenAI Context Engine — simulates fraud outside the payment API (Phase: GenAI lifecycle).

Covers prompt injection, social engineering, deepfake KYC, agent tool abuse, etc.
via feature-level proxies that feed the Risk Engine and evidence buffer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# Capability ID → default proxy feature contributions
CAPABILITY_PROXY_FEATURES: Dict[str, Dict[str, float]] = {
    "CAP-0008": {"agentic_planning_score": 0.75, "agent_goal_anomaly": 0.70},
    "CAP-0009": {"agentic_tool_abuse_score": 0.80, "unauthorized_tool_call_risk": 0.78},
    "CAP-0010": {"prompt_injection_risk": 0.85, "goal_hacking_score": 0.82},
    "CAP-0011": {"memory_poisoning_score": 0.72, "context_poisoning_score": 0.70},
    "CAP-0012": {"social_engineering_score": 0.78, "phishing_content_risk": 0.75},
    "CAP-0005": {"deepfake_identity_score": 0.80, "biometric_spoof_risk": 0.76},
    "CAP-0006": {"voice_cloning_score": 0.77, "vishing_risk": 0.74},
    "CAP-0007": {"document_forgery_score": 0.79, "synthetic_document_risk": 0.77},
    "CAP-0015": {"biometric_synthesis_score": 0.73},
}

CHANNEL_BOOST: Dict[str, str] = {
    "voice": "vishing_risk",
    "phone": "vishing_risk",
    "email": "phishing_content_risk",
    "sms": "phishing_content_risk",
    "video": "deepfake_identity_score",
    "agent": "agentic_tool_abuse_score",
    "web": "prompt_injection_risk",
}


class GenAIContextEngine:
    """Score GenAI attack context from payload proxies and KB capability IDs."""

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        features = dict(payload.get("genai_features") or {})
        capability_ids = payload.get("capability_ids") or payload.get("genai_capability_ids") or []
        channels = payload.get("channels") or payload.get("channel") or []
        if isinstance(channels, str):
            channels = [channels]

        for cap_id in capability_ids:
            for key, val in CAPABILITY_PROXY_FEATURES.get(cap_id, {}).items():
                features[key] = max(float(features.get(key, 0)), val)

        for channel in channels:
            key = CHANNEL_BOOST.get(str(channel).lower())
            if key:
                features[key] = max(float(features.get(key, 0)), 0.65)

        if payload.get("victim_coerced"):
            features["victim_coerced"] = 1.0
            features["social_engineering_score"] = max(
                float(features.get("social_engineering_score", 0)), 0.82
            )
        if payload.get("agent_mediated"):
            features["agent_mediated_payment"] = 1.0
            features["agentic_tool_abuse_score"] = max(
                float(features.get("agentic_tool_abuse_score", 0)), 0.75
            )

        family_id = payload.get("attack_family") or payload.get("family_id") or ""
        if family_id.startswith("AG"):
            features.setdefault("prompt_injection_risk", 0.70)
            features.setdefault("agent_goal_anomaly", 0.68)
        elif family_id.startswith("SEP"):
            features.setdefault("social_engineering_score", 0.80)
            features.setdefault("victim_coerced", 1.0)
        elif family_id.startswith("ATO"):
            features.setdefault("document_forgery_score", 0.72)
            features.setdefault("recovery_fraud_risk", 0.70)

        risk = self._aggregate_risk(features)
        triggered: List[str] = []
        if features.get("prompt_injection_risk", 0) >= 0.65:
            triggered.append("genai_prompt_injection")
        if features.get("social_engineering_score", 0) >= 0.65:
            triggered.append("genai_social_engineering")
        if features.get("vishing_risk", 0) >= 0.60:
            triggered.append("genai_vishing")
        if features.get("deepfake_identity_score", 0) >= 0.60:
            triggered.append("genai_deepfake_identity")
        if features.get("agentic_tool_abuse_score", 0) >= 0.65:
            triggered.append("genai_agent_tool_abuse")
        if features.get("victim_coerced"):
            triggered.append("genai_victim_coerced")

        return {
            "status": "PASS",
            "genai_features": features,
            "genai_risk_contribution": round(risk, 4),
            "triggered_rules": triggered,
            "channels": channels,
            "capability_ids": capability_ids,
        }

    @staticmethod
    def _aggregate_risk(features: Dict[str, Any]) -> float:
        scores = [
            float(features.get(k, 0))
            for k in (
                "prompt_injection_risk",
                "social_engineering_score",
                "vishing_risk",
                "deepfake_identity_score",
                "agentic_tool_abuse_score",
                "document_forgery_score",
                "memory_poisoning_score",
                "victim_coerced",
            )
        ]
        return min(1.0, max(scores) * 0.85 + sum(scores) / max(len(scores), 1) * 0.15)
