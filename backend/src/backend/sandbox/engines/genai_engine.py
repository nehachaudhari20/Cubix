"""
KB-driven GenAI Engine — 4-step pipeline per architecture spec.

INPUT:  attack_family_id, variant_id, payload, sandbox_state
STEP 1: Load family, variant, capabilities, classification, signals, mappings from KB
STEP 2: Compute GenAI feature vector (50+ features)
STEP 3: Apply family/variant weights from KB relationships
STEP 4: Score risk (weighted sum + load-bearing/amplified bonuses)
OUTPUT: EngineResult (status, risk_contribution, evidence)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from backend.knowledge.canonical_loader import CanonicalKnowledgeLoader

# All GenAI-scored feature names (50+)
GENAI_FEATURE_NAMES: tuple[str, ...] = (
    "prompt_injection_risk",
    "goal_hacking_score",
    "agentic_planning_score",
    "agentic_tool_abuse_score",
    "memory_poisoning_score",
    "social_engineering_score",
    "phishing_content_risk",
    "vishing_risk",
    "voice_cloning_score",
    "deepfake_identity_score",
    "biometric_spoof_risk",
    "document_forgery_score",
    "synthetic_identity_score",
    "cross_stage_composition_score",
    "adaptive_evasion_score",
    "synthetic_content_score",
    "personalization_score",
    "scale_automation_score",
    "model_evasion_score",
    "network_orchestration_score",
    "biometric_synthesis_score",
    "agent_goal_anomaly",
    "unauthorized_tool_call_risk",
    "context_poisoning_score",
    "synthetic_document_risk",
    "victim_coerced",
    "agent_mediated_payment",
    "recovery_fraud_risk",
    "hidden_instruction_density",
    "tool_call_anomaly_score",
    "memory_integrity_risk",
    "channel_spoof_risk",
    "liveness_bypass_score",
    "kyc_deepfake_risk",
    "voice_auth_bypass_score",
    "document_template_match_score",
    "identity_consistency_score",
    "multi_stage_coordination_score",
    "threshold_hugging_score",
    "behavioral_camouflage_score",
    "bec_content_risk",
    "romance_scam_score",
    "digital_arrest_score",
    "agent_shopping_score",
    "api_manipulation_score",
    "webhook_spoof_risk",
    "mule_recruitment_score",
    "fraud_ring_coordination_score",
    "aml_model_poisoning_score",
    "label_flipping_risk",
    "cross_channel_consistency_risk",
    "genai_load_bearing_flag",
    "genai_amplified_flag",
)

# Capability ID → base feature contributions
CAPABILITY_FEATURES: Dict[str, Dict[str, float]] = {
    "CAP-0001": {"synthetic_content_score": 0.72, "phishing_content_risk": 0.68},
    "CAP-0002": {"personalization_score": 0.75, "phishing_content_risk": 0.70, "bec_content_risk": 0.72},
    "CAP-0003": {"scale_automation_score": 0.70, "network_orchestration_score": 0.65},
    "CAP-0004": {"adaptive_evasion_score": 0.78, "threshold_hugging_score": 0.74, "behavioral_camouflage_score": 0.72},
    "CAP-0005": {"deepfake_identity_score": 0.80, "biometric_spoof_risk": 0.76, "kyc_deepfake_risk": 0.78, "liveness_bypass_score": 0.74},
    "CAP-0006": {"voice_cloning_score": 0.77, "vishing_risk": 0.74, "voice_auth_bypass_score": 0.73},
    "CAP-0007": {"document_forgery_score": 0.79, "synthetic_document_risk": 0.77, "document_template_match_score": 0.75},
    "CAP-0008": {"agentic_planning_score": 0.75, "agent_goal_anomaly": 0.70, "multi_stage_coordination_score": 0.68},
    "CAP-0009": {"agentic_tool_abuse_score": 0.80, "unauthorized_tool_call_risk": 0.78, "api_manipulation_score": 0.76, "agent_shopping_score": 0.72},
    "CAP-0010": {"prompt_injection_risk": 0.85, "goal_hacking_score": 0.82, "hidden_instruction_density": 0.80},
    "CAP-0011": {"memory_poisoning_score": 0.72, "context_poisoning_score": 0.70, "memory_integrity_risk": 0.71},
    "CAP-0012": {"social_engineering_score": 0.78, "phishing_content_risk": 0.75, "bec_content_risk": 0.70, "romance_scam_score": 0.68, "digital_arrest_score": 0.72},
    "CAP-0013": {"model_evasion_score": 0.74, "aml_model_poisoning_score": 0.70, "label_flipping_risk": 0.68},
    "CAP-0014": {"network_orchestration_score": 0.76, "fraud_ring_coordination_score": 0.74, "mule_recruitment_score": 0.70},
    "CAP-0015": {"biometric_synthesis_score": 0.73, "biometric_spoof_risk": 0.71, "identity_consistency_score": 0.69},
}

# Family-specific feature weight multipliers (from KB relationships / domain law)
FAMILY_FEATURE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "AG-001": {"prompt_injection_risk": 1.5, "goal_hacking_score": 1.4, "agentic_tool_abuse_score": 1.3},
    "AG-002": {"agentic_planning_score": 1.3, "deepfake_identity_score": 1.2, "agentic_tool_abuse_score": 1.25},
    "SEP-001": {"social_engineering_score": 1.4, "phishing_content_risk": 1.3, "vishing_risk": 1.2},
    "AML-001": {"adaptive_evasion_score": 1.2, "model_evasion_score": 1.15, "threshold_hugging_score": 1.1},
}

# Prefix fallbacks when family not explicitly listed
PREFIX_FEATURE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "AG": {"prompt_injection_risk": 1.3, "agentic_tool_abuse_score": 1.2, "agentic_planning_score": 1.15},
    "SEP": {"social_engineering_score": 1.35, "vishing_risk": 1.2, "phishing_content_risk": 1.25},
    "ATO": {"document_forgery_score": 1.3, "recovery_fraud_risk": 1.25, "deepfake_identity_score": 1.15},
    "AML": {"adaptive_evasion_score": 1.2, "model_evasion_score": 1.15},
    "ACQ": {"network_orchestration_score": 1.2, "api_manipulation_score": 1.15},
    "MUL": {"mule_recruitment_score": 1.3, "network_orchestration_score": 1.2},
}

# Variant slug → feature boost
VARIANT_SLUG_BOOSTS: Dict[str, Dict[str, float]] = {
    "visual_prompt_injection": {"prompt_injection_risk": 1.25, "hidden_instruction_density": 1.2},
    "unauthorized_tool_calls": {"agentic_tool_abuse_score": 1.3, "unauthorized_tool_call_risk": 1.25},
    "agent_mediated_payment_fraud": {"agent_mediated_payment": 1.0, "agentic_tool_abuse_score": 1.2},
    "agentic_carding": {"agent_shopping_score": 1.3, "scale_automation_score": 1.15},
    "merchant_side_manipulation": {"api_manipulation_score": 1.2, "webhook_spoof_risk": 1.15},
    "voice_cloning_vishing": {"vishing_risk": 1.3, "voice_cloning_score": 1.25},
    "deepfake_kyc": {"kyc_deepfake_risk": 1.3, "deepfake_identity_score": 1.25},
    "synthetic_identity": {"synthetic_identity_score": 1.3, "identity_consistency_score": 0.85},
}

CHANNEL_BOOST: Dict[str, str] = {
    "voice": "vishing_risk",
    "phone": "vishing_risk",
    "email": "phishing_content_risk",
    "sms": "phishing_content_risk",
    "video": "deepfake_identity_score",
    "agent": "agentic_tool_abuse_score",
    "web": "prompt_injection_risk",
    "chat": "social_engineering_score",
}


@dataclass
class EngineResult:
    status: str
    risk_contribution: float
    evidence: Dict[str, Any] = field(default_factory=dict)
    genai_features: Dict[str, float] = field(default_factory=dict)
    triggered_rules: List[str] = field(default_factory=list)


class GenAIEngine:
    """KB-driven GenAI scoring engine."""

    LOAD_BEARING_MULTIPLIER = 1.3
    AMPLIFIED_MULTIPLIER = 1.1

    def __init__(self, kb: Optional[CanonicalKnowledgeLoader] = None):
        self.kb = kb or CanonicalKnowledgeLoader()

    def evaluate(
        self,
        attack_family_id: str,
        variant_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        sandbox_state: Optional[Any] = None,
    ) -> EngineResult:
        payload = payload or {}
        family_id = attack_family_id or payload.get("attack_family") or payload.get("family_id") or ""
        variant_id = variant_id or payload.get("variant_id")

        # STEP 1: Load from KB
        ctx = self._load_kb_context(family_id, variant_id)

        # STEP 2: Compute feature vector
        features = self._compute_feature_vector(ctx, payload, sandbox_state)

        # STEP 3: Apply family weights
        weighted = self._apply_family_weights(features, ctx)

        # STEP 4: Score risk
        risk, evidence = self._score_risk(weighted, ctx, payload)

        triggered = self._trigger_rules(weighted)
        status = "PASS" if risk < 0.75 else ("CHALLENGE" if risk < 0.90 else "BLOCK")

        return EngineResult(
            status=status,
            risk_contribution=round(risk, 4),
            evidence={
                **evidence,
                "attack_family_id": family_id,
                "variant_id": variant_id,
                "capability_ids": ctx.get("capability_ids") or [],
                "signal_ids": ctx.get("signal_ids") or [],
                "classification": ctx.get("classification"),
                "load_bearing": ctx.get("load_bearing"),
                "channels": payload.get("channels") or payload.get("channel") or [],
            },
            genai_features=weighted,
            triggered_rules=triggered,
        )

    def _load_kb_context(self, family_id: str, variant_id: Optional[str]) -> Dict[str, Any]:
        family = self.kb.get_family(family_id) if family_id else None
        variant = self.kb.get_variant(variant_id) if variant_id else None

        genai = (family or {}).get("genai") or {}
        capability_ids = list(genai.get("capability_ids") or [])
        classification = genai.get("classification") or (family or {}).get("genai_classification")
        load_bearing = bool(genai.get("load_bearing") or (family or {}).get("genai_load_bearing"))

        signals = self.kb.get_family_signals(family_id) if family_id else []
        signal_ids = [s.get("signal_id") for s in signals if s.get("signal_id")]

        feature_names: Set[str] = set()
        for sig_id in signal_ids:
            feature_names.update(self.kb.get_signal_features(sig_id))

        cross_stages = (family or {}).get("cross_stage_lifecycle_stage_ids") or []
        if len(cross_stages) >= 2:
            capability_ids.append("__cross_stage__")

        return {
            "family": family,
            "variant": variant,
            "capability_ids": capability_ids,
            "classification": classification,
            "load_bearing": load_bearing,
            "amplified": classification == "genai_amplified",
            "signal_ids": signal_ids,
            "signals": signals,
            "mapped_feature_names": sorted(feature_names),
            "cross_stage_count": len(cross_stages),
            "variant_slug": (variant or {}).get("slug") or "",
        }

    def _compute_feature_vector(
        self,
        ctx: Dict[str, Any],
        payload: Dict[str, Any],
        sandbox_state: Optional[Any],
    ) -> Dict[str, float]:
        features: Dict[str, float] = {name: 0.0 for name in GENAI_FEATURE_NAMES}

        # Payload overrides / hints
        for key, val in (payload.get("genai_features") or {}).items():
            if key in features:
                features[key] = max(features[key], float(val))

        # Capability contributions
        for cap_id in ctx.get("capability_ids") or []:
            if cap_id == "__cross_stage__":
                features["cross_stage_composition_score"] = max(
                    features["cross_stage_composition_score"], 0.72 + 0.03 * ctx.get("cross_stage_count", 2)
                )
                features["multi_stage_coordination_score"] = max(
                    features["multi_stage_coordination_score"], 0.68
                )
                continue
            for fname, base in CAPABILITY_FEATURES.get(cap_id, {}).items():
                features[fname] = max(features[fname], base)

        # Observable signals → proxy activation on mapped features
        for fname in ctx.get("mapped_feature_names") or []:
            if fname in features:
                features[fname] = max(features[fname], 0.55)
            elif fname.startswith("genai_") or fname.endswith("_score") or fname.endswith("_risk"):
                features[fname] = max(features.get(fname, 0), 0.55)

        # Channel boosts
        channels = payload.get("channels") or payload.get("channel") or []
        if isinstance(channels, str):
            channels = [channels]
        for channel in channels:
            key = CHANNEL_BOOST.get(str(channel).lower())
            if key:
                features[key] = max(features[key], 0.65)

        # Payload behavioral flags
        if payload.get("victim_coerced"):
            features["victim_coerced"] = 1.0
            features["social_engineering_score"] = max(features["social_engineering_score"], 0.82)
        if payload.get("agent_mediated"):
            features["agent_mediated_payment"] = 1.0
            features["agentic_tool_abuse_score"] = max(features["agentic_tool_abuse_score"], 0.75)

        # Sandbox state hints
        if sandbox_state is not None:
            if getattr(sandbox_state, "genai_context", None):
                for key, val in sandbox_state.genai_context.items():
                    if key in features:
                        features[key] = max(features[key], float(val))

        # Classification flags as features
        if ctx.get("load_bearing"):
            features["genai_load_bearing_flag"] = 1.0
        if ctx.get("amplified"):
            features["genai_amplified_flag"] = 1.0

        # Synthetic identity heuristic when multiple identity capabilities present
        id_caps = {"CAP-0005", "CAP-0007", "CAP-0015"} & set(ctx.get("capability_ids") or [])
        if len(id_caps) >= 2:
            features["synthetic_identity_score"] = max(features["synthetic_identity_score"], 0.75)

        return features

    def _apply_family_weights(self, features: Dict[str, float], ctx: Dict[str, Any]) -> Dict[str, float]:
        family = ctx.get("family") or {}
        family_id = family.get("attack_id") or ""
        weights = dict(FAMILY_FEATURE_WEIGHTS.get(family_id) or {})

        if not weights and family_id:
            prefix = family_id.split("-")[0]
            weights.update(PREFIX_FEATURE_WEIGHTS.get(prefix, {}))

        variant_slug = ctx.get("variant_slug") or ""
        if variant_slug in VARIANT_SLUG_BOOSTS:
            for fname, mult in VARIANT_SLUG_BOOSTS[variant_slug].items():
                if fname in features:
                    features[fname] = min(1.0, features[fname] * mult)

        weighted = dict(features)
        for fname, mult in weights.items():
            if fname in weighted and weighted[fname] > 0:
                weighted[fname] = min(1.0, weighted[fname] * mult)

        return weighted

    def _score_risk(
        self,
        features: Dict[str, float],
        ctx: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> tuple[float, Dict[str, Any]]:
        # Weighted sum over active GenAI features (exclude flag features from sum)
        scoring_keys = [
            k for k in GENAI_FEATURE_NAMES
            if k not in ("genai_load_bearing_flag", "genai_amplified_flag") and features.get(k, 0) > 0
        ]
        if not scoring_keys:
            return 0.0, {"base_score": 0.0, "active_features": 0}

        base = sum(features[k] for k in scoring_keys) / len(scoring_keys)

        multiplier = 1.0
        bonuses: List[str] = []
        if ctx.get("load_bearing"):
            multiplier *= self.LOAD_BEARING_MULTIPLIER
            bonuses.append("load_bearing")
        if ctx.get("amplified"):
            multiplier *= self.AMPLIFIED_MULTIPLIER
            bonuses.append("amplified")

        variant_adj = 1.0
        variant = ctx.get("variant") or {}
        if variant.get("sandbox_executable") is False and ctx.get("load_bearing"):
            variant_adj = 1.05  # non-exec load-bearing families score slightly higher in proxy mode

        risk = min(1.0, base * multiplier * variant_adj)

        return risk, {
            "base_score": round(base, 4),
            "multiplier": round(multiplier, 4),
            "variant_adjustment": round(variant_adj, 4),
            "bonuses_applied": bonuses,
            "active_features": len(scoring_keys),
            "scoring_features": scoring_keys[:20],
        }

    @staticmethod
    def _trigger_rules(features: Dict[str, float]) -> List[str]:
        triggered: List[str] = []
        checks = [
            ("prompt_injection_risk", 0.65, "genai_prompt_injection"),
            ("social_engineering_score", 0.65, "genai_social_engineering"),
            ("vishing_risk", 0.60, "genai_vishing"),
            ("deepfake_identity_score", 0.60, "genai_deepfake_identity"),
            ("agentic_tool_abuse_score", 0.65, "genai_agent_tool_abuse"),
            ("adaptive_evasion_score", 0.60, "genai_adaptive_evasion"),
            ("document_forgery_score", 0.60, "genai_document_forgery"),
            ("cross_stage_composition_score", 0.65, "genai_cross_stage"),
        ]
        for key, threshold, rule in checks:
            if features.get(key, 0) >= threshold:
                triggered.append(rule)
        if features.get("victim_coerced"):
            triggered.append("genai_victim_coerced")
        return triggered
