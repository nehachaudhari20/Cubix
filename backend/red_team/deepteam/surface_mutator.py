"""
Surface mutation engine — the non-payment analogue of PaymentAttackEngine.

Before this module, mutation only applied to `initiate_payment` steps, so every
non-payment surface ran exactly one full-strength attack and was blocked. ASR on
those surfaces was structurally 0%, and Blue received no bypassed rows to learn
from.

An attack on a control surface has three kinds of attacker-controlled knob:

  intensity   continuous GenAI feature scores (prompt_injection_risk, ...). Some
              are *inverted* — identity_consistency_score and behavioural_variance
              go DOWN as the attack gets more aggressive.
  toggles     discrete capabilities the attacker either uses or does not
              (remote_access_active, stolen_token, recovery_flow). These cause
              step-changes in the verdict, so ablating them individually is what
              finds a stealth path.
  ladders     numeric parameters with an aggressive and a stealth end
              (requested_amount vs the agent's spend limit, consent scope count,
              interaction timing, ring size).

The space below is derived from what the surface engines in
backend/sandbox/engines/ actually read, so every knob moves a real control.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Ladder:
    """A numeric parameter with an aggressive end and a stealth end."""

    param: str
    aggressive: Any
    stealth: Any

    def at(self, intensity: float) -> Any:
        """Interpolate; keeps ints as ints so payload types stay sane."""
        try:
            a, s = float(self.aggressive), float(self.stealth)
        except (TypeError, ValueError):
            return self.aggressive if intensity >= 0.5 else self.stealth
        value = s + (a - s) * intensity
        if isinstance(self.aggressive, int) and isinstance(self.stealth, int):
            return int(round(value))
        return round(value, 4)


@dataclass(frozen=True)
class MutationSpace:
    """Attacker-controlled knobs for one surface."""

    surface: str
    intensity_features: Tuple[str, ...] = ()
    # Features where a LOWER value is the more aggressive attack.
    inverted_features: Tuple[str, ...] = ()
    # (param, aggressive_value, stealth_value)
    toggles: Tuple[Tuple[str, Any, Any], ...] = ()
    ladders: Tuple[Ladder, ...] = ()
    # (param, [values...]) — categorical choices worth probing
    categoricals: Tuple[Tuple[str, Tuple[Any, ...]], ...] = ()

    def features_at(self, intensity: float) -> Dict[str, float]:
        out: Dict[str, float] = {f: round(intensity, 4) for f in self.intensity_features}
        for f in self.inverted_features:
            out[f] = round(1.0 - intensity, 4)
        return out

    def toggles_at(self, intensity: float) -> Dict[str, Any]:
        """Toggles engage above the midpoint — they are all-or-nothing capabilities."""
        engaged = intensity >= 0.5
        return {param: (agg if engaged else stealth) for param, agg, stealth in self.toggles}

    def ladders_at(self, intensity: float) -> Dict[str, Any]:
        return {ladder.param: ladder.at(intensity) for ladder in self.ladders}

    def payload_at(self, intensity: float) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        payload.update(self.toggles_at(intensity))
        payload.update(self.ladders_at(intensity))
        payload["genai_features"] = self.features_at(intensity)
        return payload


SURFACE_MUTATION_SPACES: Dict[str, MutationSpace] = {
    "agent": MutationSpace(
        surface="agent",
        intensity_features=(
            "prompt_injection_risk",
            "goal_hacking_score",
            "hidden_instruction_density",
            "memory_poisoning_score",
            "context_poisoning_score",
            "agentic_tool_abuse_score",
            "unauthorized_tool_call_risk",
            "api_manipulation_score",
            "adaptive_evasion_score",
        ),
        toggles=(
            ("agent_verified", False, True),
            ("counterparty_agent_unverified", True, False),
            ("a2a_channel", True, False),
            ("a2a_channel_authenticated", False, True),
        ),
        ladders=(
            # Stay under the 25k mandate limit at the stealth end.
            Ladder("requested_amount", 40000, 5000),
            Ladder("spend_limit", 25000, 25000),
        ),
        categoricals=(
            ("requested_tools", (("payment_api",), ("search",), ("search", "checkout"))),
        ),
    ),
    "auth_se": MutationSpace(
        surface="auth_se",
        intensity_features=(
            "social_engineering_score",
            "phishing_content_risk",
            "vishing_risk",
            "voice_cloning_score",
            "bec_content_risk",
            "channel_spoof_risk",
            "recovery_fraud_risk",
        ),
        toggles=(
            ("victim_coerced", True, False),
            ("recovery_flow", True, False),
        ),
        categoricals=(
            ("channel", ("voice", "email", "sms", "web")),
            ("authentication_method", ("otp", "password", "biometric")),
        ),
    ),
    "kyc": MutationSpace(
        surface="kyc",
        intensity_features=(
            "deepfake_identity_score",
            "kyc_deepfake_risk",
            "biometric_spoof_risk",
            "liveness_bypass_score",
            "document_forgery_score",
            "document_template_match_score",
            "synthetic_identity_score",
        ),
        inverted_features=("identity_consistency_score",),
        categoricals=(
            (
                "evidence_type",
                ("video_kyc", "biometric", "liveness", "document", "recovery_document"),
            ),
        ),
    ),
    "open_banking": MutationSpace(
        surface="open_banking",
        intensity_features=("personalization_score", "synthetic_content_score"),
        toggles=(
            ("tpp_licensed", False, True),
            ("stolen_token", True, False),
            ("tpp_registration", True, False),
        ),
        ladders=(
            Ladder("tpp_registration_age_days", 3, 500),
            Ladder("tpp_risk_score", 0.85, 0.10),
        ),
        categoricals=(
            (
                "scopes",
                (
                    ("accounts.read", "accounts.write", "payments.initiate", "data.export_all"),
                    ("accounts.read", "payments.initiate"),
                    ("accounts.read", "accounts.write"),
                    ("accounts.read",),
                ),
            ),
        ),
    ),
    "device": MutationSpace(
        surface="device",
        intensity_features=(
            "scale_automation_score",
            "behavioral_camouflage_score",
            "biometric_synthesis_score",
        ),
        toggles=(
            ("remote_access_active", True, False),
            ("accessibility_service_active", True, False),
            ("screen_overlay_active", True, False),
            ("headless_client", True, False),
        ),
        ladders=(
            # Human-plausible interaction timing and jitter at the stealth end.
            Ladder("mean_interaction_interval_ms", 30, 400),
            Ladder("behavioural_variance", 0.02, 0.55),
        ),
    ),
    "network": MutationSpace(
        surface="network",
        intensity_features=(
            "fraud_ring_coordination_score",
            "network_orchestration_score",
            "multi_stage_coordination_score",
            "mule_recruitment_score",
            "aml_model_poisoning_score",
            "label_flipping_risk",
        ),
        toggles=(("aml_narrative_submitted", True, False),),
        ladders=(Ladder("ring_size", 12, 2),),
    ),
}


@dataclass
class SurfaceVariation:
    """One concrete probe against a surface."""

    variation_id: str
    label: str
    action_payload: Dict[str, Any]
    intensity: Optional[float] = None
    kind: str = "intensity"  # intensity | ablation | categorical | combo
    metadata: Dict[str, Any] = field(default_factory=dict)


class SurfaceAttackEngine:
    """Generate probe variations for a non-payment control surface."""

    # Coarse ladder; the adaptive search refines around the boundary it finds.
    DEFAULT_INTENSITIES = (0.15, 0.30, 0.45, 0.60, 0.80, 0.95)

    def __init__(self, max_variations: int = 24):
        self.max_variations = max(4, max_variations)

    def generate(
        self,
        surface: str,
        base_payload: Dict[str, Any],
        intensities: Optional[Sequence[float]] = None,
    ) -> List[SurfaceVariation]:
        space = SURFACE_MUTATION_SPACES.get(surface)
        if space is None:
            return []

        variations: List[SurfaceVariation] = []

        def add(label: str, payload: Dict[str, Any], **kwargs) -> None:
            if len(variations) >= self.max_variations:
                return
            variations.append(
                SurfaceVariation(
                    variation_id=f"svar_{uuid.uuid4().hex[:8]}",
                    label=label,
                    action_payload=payload,
                    **kwargs,
                )
            )

        # --- 1. intensity ladder: the continuous evasion axis -----------------
        for intensity in (intensities or self.DEFAULT_INTENSITIES):
            add(
                f"intensity_{intensity:.2f}",
                self.apply(space, base_payload, intensity),
                intensity=intensity,
                kind="intensity",
            )

        # --- 2. toggle ablations at full intensity ----------------------------
        # A single capability can be the sole cause of a hard block. Dropping one
        # at a time shows which control is actually doing the work.
        for param, aggressive, stealth in space.toggles:
            payload = self.apply(space, base_payload, 0.95)
            payload[param] = stealth
            add(
                f"ablate_{param}",
                payload,
                intensity=0.95,
                kind="ablation",
                metadata={"ablated": param},
            )

        # --- 3. categorical probes at mid intensity ---------------------------
        for param, options in space.categoricals:
            for option in options:
                payload = self.apply(space, base_payload, 0.55)
                payload[param] = list(option) if isinstance(option, tuple) else option
                label_value = option[0] if isinstance(option, tuple) else option
                add(
                    f"{param}_{label_value}",
                    payload,
                    intensity=0.55,
                    kind="categorical",
                    metadata={param: option},
                )

        # --- 4. combo: all toggles off, low intensity, safest categoricals ----
        stealth = self.apply(space, base_payload, 0.20)
        for param, options in space.categoricals:
            if options:
                last = options[-1]
                stealth[param] = list(last) if isinstance(last, tuple) else last
        add("combo_full_stealth", stealth, intensity=0.20, kind="combo")

        return variations

    @staticmethod
    def apply(
        space: MutationSpace,
        base_payload: Dict[str, Any],
        intensity: float,
    ) -> Dict[str, Any]:
        """Overlay the mutation space at `intensity` onto the planner's payload."""
        payload = deepcopy(base_payload)
        mutated = space.payload_at(intensity)

        # GenAI features merge rather than replace, so family-specific keys the
        # planner set (and the KB profile) survive alongside the scaled ones.
        features = dict(payload.get("genai_features") or {})
        features.update(mutated.pop("genai_features", {}))
        payload["genai_features"] = features
        payload.update(mutated)
        payload["mutation_intensity"] = round(intensity, 4)
        return payload

    @staticmethod
    def space_for(surface: str) -> Optional[MutationSpace]:
        return SURFACE_MUTATION_SPACES.get(surface)
