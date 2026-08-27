"""
Surface adjudicator — one path, every non-payment control surface.

The point of this module is that granularity comes from **data, not code**. A
surface handler does three things:

  1. run its surface engine (agent trust, social engineering, KYC evidence, ...)
  2. run the KB GenAI engine for the attacking family's feature vector
  3. evaluate the KB rule set filtered to this surface's engine name, and compare
     what fired against the family's own `targeted_control_ids`

So 21 KB families with 21 distinct control sets get 21 distinct verdicts through
7 handlers, because the control identity lives in the KB (family
`targeted_control_ids` + `rules.json`), not in Python branches.

Every surface returns the same `SandboxObservation` shape as `initiate_payment`,
which is what lets Blue treat all surfaces as one evidence stream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .rules.compiled_controls import CompiledControlSet
from .rules.rule_engine import RuleEngine
from .schemas import JourneyStep


@dataclass(frozen=True)
class SurfaceSpec:
    """Static description of one adjudicated surface."""

    surface: str
    entry_action: str
    engine_name: str          # matches `engines` in rules.json
    journey_step: str
    stage_id: str
    risk_key: str             # engine result key holding the surface risk
    registry: str             # EXECUTABLE_DEFAULTS key for thresholds


SURFACE_SPECS: Dict[str, SurfaceSpec] = {
    "agent": SurfaceSpec(
        surface="agent",
        entry_action="simulate_genai_context",
        engine_name="agent",
        journey_step="AI Agent Commerce",
        stage_id="STG-0001",
        risk_key="agent_risk",
        registry="agent",
    ),
    "auth_se": SurfaceSpec(
        surface="auth_se",
        entry_action="simulate_social_engineering",
        engine_name="auth_se",
        journey_step="Authentication / Social Engineering",
        stage_id="STG-0004",
        risk_key="auth_se_risk",
        registry="auth_se",
    ),
    "kyc": SurfaceSpec(
        surface="kyc",
        entry_action="submit_kyc_evidence",
        engine_name="kyc_genai",
        journey_step="Identity / KYC Evidence",
        stage_id="STG-0019",
        risk_key="kyc_risk",
        registry="kyc_genai",
    ),
    "open_banking": SurfaceSpec(
        surface="open_banking",
        entry_action="request_consent",
        engine_name="consent",
        journey_step="Third Party / Open Banking",
        stage_id="STG-0042",
        risk_key="consent_risk",
        registry="consent",
    ),
    "device": SurfaceSpec(
        surface="device",
        entry_action="establish_session",
        engine_name="session_integrity",
        journey_step="Device / Session",
        stage_id="STG-0028",
        risk_key="session_risk",
        registry="session_integrity",
    ),
    "network": SurfaceSpec(
        surface="network",
        entry_action="orchestrate_network",
        engine_name="network",
        journey_step="Cross-Stage Network",
        stage_id="STG-0048",
        risk_key="network_risk",
        registry="network",
    ),
}


@dataclass
class SurfaceVerdict:
    """Adjudication result, ready to become a SandboxObservation."""

    decision: str
    reason: str
    risk_score: float
    rule_risk: float
    surface_risk: float
    control_triggers: List[str]
    control_gaps: Dict[str, Any]
    journey: List[JourneyStep]
    state_snapshot: Dict[str, Any]
    engine_result: Dict[str, Any]
    genai_result: Dict[str, Any]


class SurfaceAdjudicator:
    """Runs surface engine + GenAI engine + KB rules and decides."""

    def __init__(
        self,
        state: Any,
        genai_engine: Any,
        compiled_controls: Optional[CompiledControlSet] = None,
        kb_path: str = "data/knowledge/canonical",
    ):
        self.state = state
        self.genai_engine = genai_engine
        self.compiled_controls = compiled_controls
        self.rule_engine = RuleEngine(compiled_controls=compiled_controls, kb_path=kb_path)

    def adjudicate(
        self,
        spec: SurfaceSpec,
        payload: Dict[str, Any],
        engine_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        family: Optional[Dict[str, Any]] = None,
    ) -> SurfaceVerdict:
        journey: List[JourneyStep] = []

        # 1. GenAI feature vector for the attacking family (KB-driven).
        #
        # The KB describes what the family is *capable* of. The payload describes
        # how hard the attacker is pushing on *this* attempt. Attacker-supplied
        # values therefore win: without that precedence the capability profile
        # pins every attempt to the same score, Red can never trade strength for
        # stealth, and Blue only ever sees blocked attacks.
        genai_result = self.genai_engine.evaluate(payload, sandbox_state=self.state)
        kb_features = genai_result.get("genai_features") or {}
        attacker_features = payload.get("genai_features") or {}
        genai_features = {**kb_features, **attacker_features}

        genai_risk = float(genai_result.get("genai_risk_contribution") or 0)
        if attacker_features:
            # Rescale the KB risk by how hard the attacker is actually pushing,
            # so a deliberately weak probe scores lower than a full-strength run.
            pushed = [float(v) for v in attacker_features.values() if isinstance(v, (int, float))]
            if pushed:
                genai_risk = min(1.0, genai_risk * (sum(pushed) / len(pushed)) / 0.75)
        genai_result = {**genai_result, "genai_features": genai_features,
                        "genai_risk_contribution": round(genai_risk, 4)}
        journey.append(JourneyStep(step="GenAI Context", result=genai_result))

        # 2. Surface engine — sees the GenAI features and mutates durable state.
        engine_payload = {**payload, "genai_features": genai_features}
        engine_result = engine_fn(engine_payload)
        journey.append(JourneyStep(step=spec.journey_step, result=engine_result))

        surface_risk = float(engine_result.get(spec.risk_key) or 0)
        engine_flags = list(engine_result.get("flags") or [])

        # 3. KB rules filtered to this surface's engine.
        context = self._build_context(spec, payload, engine_result, genai_features, family)
        expected_controls = list(
            (family or {}).get("targeted_control_ids")
            or payload.get("expected_controls")
            or payload.get("targeted_control_ids")
            or []
        )
        rule_result = self.rule_engine.evaluate(
            context,
            expected_controls=expected_controls,
            engines=[spec.engine_name],
        )
        journey.append(
            JourneyStep(
                step="Rule Engine",
                result={
                    "engine": spec.engine_name,
                    "risk_contribution": rule_result.risk_contribution,
                    "triggered_rules": rule_result.triggered_rules,
                    "triggered_controls": rule_result.triggered_controls,
                    "triggered_signals": rule_result.triggered_signals,
                },
            )
        )

        rule_risk = float(rule_result.risk_contribution)

        # Blend: KB rules lead, surface engine and GenAI context contribute.
        risk_score = min(1.0, 0.45 * rule_risk + 0.35 * surface_risk + 0.20 * genai_risk)

        triggers = engine_flags + list(rule_result.triggered_rules)
        triggers.extend(rule_result.triggered_controls)
        if self.compiled_controls is not None:
            triggers = self.compiled_controls.resolve_triggers(triggers)

        decision, reason = self._decide(spec, risk_score, engine_result)

        state_snapshot = {
            "surface": spec.surface,
            "stage_id": spec.stage_id,
            "genai_features": genai_features,
            "capability_ids": genai_result.get("capability_ids") or [],
            "channels": genai_result.get("channels") or [],
            "attack_family": payload.get("attack_family"),
            "triggered_signals": rule_result.triggered_signals,
            "control_gaps": rule_result.control_gaps,
            "surface_risk": round(surface_risk, 4),
            "rule_risk": round(rule_risk, 4),
            "genai_risk": round(genai_risk, 4),
        }
        # Surface-specific state the collector turns into features.
        for key, value in engine_result.items():
            if key in ("flags", "status", "engine", "stage"):
                continue
            state_snapshot.setdefault(key, value)

        self.state.record_surface_event(
            {
                "surface": spec.surface,
                "customer_id": payload.get("customer_id"),
                "attack_family": payload.get("attack_family"),
                "technique": payload.get("technique"),
                "decision": decision,
                "risk_score": round(risk_score, 4),
                "flags": engine_flags,
            }
        )

        return SurfaceVerdict(
            decision=decision,
            reason=reason,
            risk_score=round(risk_score, 4),
            rule_risk=round(rule_risk, 4),
            surface_risk=round(surface_risk, 4),
            control_triggers=triggers,
            control_gaps=rule_result.control_gaps,
            journey=journey,
            state_snapshot=state_snapshot,
            engine_result=engine_result,
            genai_result=genai_result,
        )

    def _build_context(
        self,
        spec: SurfaceSpec,
        payload: Dict[str, Any],
        engine_result: Dict[str, Any],
        genai_features: Dict[str, Any],
        family: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Flat field namespace the declarative rule conditions read from."""
        context: Dict[str, Any] = {
            "surface": spec.surface,
            "stage_id": spec.stage_id,
            "signal_context_active": True,
            "family_signal_ids": list(
                (family or {}).get("observable_signal_ids")
                or payload.get("family_signal_ids")
                or []
            ),
            "expected_controls": list((family or {}).get("targeted_control_ids") or []),
            "attack_family": payload.get("attack_family"),
            "technique": payload.get("technique"),
            "channel": payload.get("channel"),
        }
        context.update(genai_features)
        # Engine outputs (minus bookkeeping) are addressable by rules directly.
        for key, value in engine_result.items():
            if key in ("flags", "status", "engine", "stage"):
                continue
            context[key] = value
        # Flags exposed both as a list (for `contains`) and as boolean fields.
        flags = list(engine_result.get("flags") or [])
        context["flags"] = flags
        for flag in flags:
            context[flag] = True
        # Customer state, so surface rules can read trust/age like payment rules do.
        customer = self.state.get_customer(payload.get("customer_id") or "")
        if customer is not None:
            context.setdefault("trust_score", customer.trust_score)
            context.setdefault("account_age_days", customer.account_age_days)
            context.setdefault("verified", customer.verified)
        # Explicit payload overrides win last.
        for key, value in payload.items():
            if key not in ("genai_features",):
                context.setdefault(key, value)
        return context

    def _decide(
        self,
        spec: SurfaceSpec,
        risk_score: float,
        engine_result: Dict[str, Any],
    ) -> tuple[str, str]:
        """Map risk to ALLOW / CHALLENGE / BLOCK using KB-resolved thresholds."""
        allow = float(
            self.rule_engine.resolve_threshold("allow_threshold", spec.registry, None)
            or self.rule_engine.resolve_threshold("allow_threshold", "authorization", 0.30)
        )
        challenge = float(
            self.rule_engine.resolve_threshold("challenge_threshold", spec.registry, None)
            or self.rule_engine.resolve_threshold("challenge_threshold", "authorization", 0.60)
        )

        # A hard engine failure blocks regardless of the blended score.
        if engine_result.get("status") == "FAIL":
            return "BLOCK", f"{spec.engine_name}_control_failed"

        if risk_score < allow:
            return "ALLOW", f"{spec.surface}_low_risk"
        if risk_score < challenge:
            return "CHALLENGE", f"{spec.surface}_step_up_required"
        return "BLOCK", f"{spec.surface}_high_risk"
