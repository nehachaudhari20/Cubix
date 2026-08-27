"""
Executable composite campaigns — attacks that cross control surfaces.

`composite_intel.COMPOSITE_ARCHETYPES` groups KB families into *hypotheses* for
the LLM planner. This module is the executable counterpart: an ordered chain of
adjudicated actions run against **one sandbox instance**, so each step sees the
state the previous step left behind.

That shared state is the whole point. A deepfake accepted at KYC sets
`verified` and raises `trust_score`, so the payment that follows is evaluated as
a trusted customer's payment. A payment-only sandbox cannot express this: it can
score the payment, but not the reason the payment looks legitimate.

Each chain is measured two ways:

  contextual  the full chain on shared state
  isolated    the final cash-out step alone, on fresh state

The delta between them is the *cross-surface uplift* — how much the upstream
attack bought the attacker. A positive uplift is a control gap that no
single-surface test would reveal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from backend.taxonomy import SURFACE_ENTRY_ACTION, resolve_technique


@dataclass(frozen=True)
class ChainStep:
    """One action in a composite chain."""

    action_type: str
    family_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class CompositeChain:
    name: str
    description: str
    steps: tuple
    # The step whose verdict decides whether the campaign succeeded.
    terminal_action: str = "initiate_payment"

    @property
    def families(self) -> List[str]:
        return [s.family_id for s in self.steps if s.family_id]

    @property
    def surfaces(self) -> List[str]:
        out: List[str] = []
        for step in self.steps:
            technique = resolve_technique(step.action_type)
            surface = technique.surface if technique else _entry_surface(step.action_type)
            if surface and surface not in out:
                out.append(surface)
        return out


#: Decision severity from the attacker's point of view (lower is better for them).
SEVERITY = {"ALLOW": 0, "PASS": 0, "CHALLENGE": 1, "BLOCK": 2, "FAIL": 2}


def _severity(decision: str) -> int:
    return SEVERITY.get(str(decision).upper(), 2)


def _entry_surface(action_type: str) -> Optional[str]:
    for surface, entry in SURFACE_ENTRY_ACTION.items():
        if entry == action_type:
            return surface
    return None


# Cash-out amount used by every chain so the isolated/contextual comparison is fair.
CASHOUT = 45000.0


COMPOSITE_CHAINS: List[CompositeChain] = [
    CompositeChain(
        name="deepfake_onboarding_to_payment",
        description=(
            "Synthetic identity onboarded via GenAI-forged evidence, then cashed out. "
            "Accepted evidence upgrades the identity, so the payment is scored as trusted."
        ),
        steps=(
            ChainStep("register_customer", payload={"trust_score": 0.30, "verified": False,
                                                   "account_age_days": 0}),
            ChainStep("register_device"),
            ChainStep("submit_synthetic_identity_onboarding", "ATO-002",
                      note="identity established under attacker control"),
            ChainStep("initiate_payment", payload={"amount": CASHOUT},
                      note="cash-out as a now-verified customer"),
        ),
    ),
    CompositeChain(
        name="vishing_to_session_to_payment",
        description=(
            "Voice-cloned call extracts the OTP, a remote-access session is established "
            "on the victim's device, and the payment is pushed from inside that session."
        ),
        steps=(
            ChainStep("register_customer", payload={"trust_score": 0.82, "verified": True,
                                                    "account_age_days": 900}),
            ChainStep("register_device"),
            ChainStep("execute_vishing_call", "AUTH-002",
                      note="credential/OTP compromise"),
            ChainStep("deploy_remote_access_trojan", "RAT-001",
                      note="session control on a known device"),
            ChainStep("initiate_payment", payload={"amount": CASHOUT},
                      note="payment from a compromised but familiar session"),
        ),
    ),
    CompositeChain(
        name="agent_hijack_to_payment",
        description=(
            "Indirect prompt injection redirects an AI agent's mandate, and the agent "
            "initiates the payment on the customer's behalf."
        ),
        steps=(
            ChainStep("register_customer", payload={"trust_score": 0.75, "verified": True,
                                                    "account_age_days": 365}),
            ChainStep("register_device"),
            ChainStep("inject_prompt_agent", "AG-001",
                      note="agent instruction fidelity broken"),
            ChainStep("initiate_payment", payload={"amount": CASHOUT, "agent_mediated": True},
                      note="agent-mediated payment"),
        ),
    ),
    CompositeChain(
        name="memory_poison_persistence",
        description=(
            "Agent memory is poisoned in one session and the payment is attempted in a "
            "later one — the attack persists in state rather than in the request."
        ),
        steps=(
            ChainStep("register_customer", payload={"trust_score": 0.78, "verified": True,
                                                    "account_age_days": 400}),
            ChainStep("register_device"),
            ChainStep("poison_agent_memory", "AG-003", note="session 1: plant the context"),
            ChainStep("poison_agent_memory", "AG-003", note="session 2: integrity degrades further"),
            ChainStep("initiate_payment", payload={"amount": CASHOUT, "agent_mediated": True},
                      note="payment under poisoned context"),
        ),
    ),
    CompositeChain(
        name="consent_abuse_to_payment",
        description=(
            "An over-broad third-party consent is granted, then scope-crept to payment "
            "initiation and used to move funds."
        ),
        steps=(
            ChainStep("register_customer", payload={"trust_score": 0.78, "verified": True,
                                                    "account_age_days": 540}),
            ChainStep("register_device"),
            ChainStep("request_broad_consent", "OB-001", note="initial grant"),
            ChainStep("abuse_consent_scope_creep", "OB-001",
                      payload={"scopes": ["accounts.read", "payments.initiate"]},
                      note="escalate the existing consent"),
            ChainStep("initiate_payment", payload={"amount": CASHOUT},
                      note="TPP-initiated payment"),
        ),
    ),
    CompositeChain(
        name="ring_orchestration_cashout",
        description=(
            "A coordinated account ring is assembled and funds are funnelled through a "
            "shared beneficiary."
        ),
        steps=(
            ChainStep("register_customer", payload={"trust_score": 0.55, "verified": True,
                                                    "account_age_days": 90}),
            ChainStep("register_device"),
            ChainStep("link_beneficiary"),
            ChainStep(
                "orchestrate_fraud_ring",
                "N-002",
                payload={"member_customer_ids": [f"C_ring_{i}" for i in range(6)]},
                note="ring assembled — members are registered so graph signals are real",
            ),
            ChainStep("initiate_payment", payload={"amount": CASHOUT},
                      note="fan-in cash-out"),
        ),
    ),
]


@dataclass
class StepOutcome:
    action_type: str
    family_id: Optional[str]
    surface: str
    decision: str
    risk_score: float
    reason: str
    control_triggers: List[str] = field(default_factory=list)
    note: str = ""


@dataclass
class CompositeResult:
    chain: str
    description: str
    surfaces: List[str]
    families: List[str]
    outcomes: List[StepOutcome] = field(default_factory=list)
    terminal_decision: str = "UNKNOWN"
    terminal_risk: float = 0.0
    isolated_decision: Optional[str] = None
    isolated_risk: Optional[float] = None
    intensity: float = 0.0
    #: Cross-surface state captured just before the cash-out step.
    upstream_effects: Dict[str, Any] = field(default_factory=dict)

    #: Effects that mean an upstream surface was genuinely compromised, as opposed
    #: to merely not being blocked. A stealthy attack that achieves nothing gives
    #: the cash-out nothing to inherit.
    COMPROMISE_KEYS = (
        "session_compromised",
        "otp_disclosed_recently",
        "victim_coerced_recently",
        "consent_payment_scope_active",
        "identity_recently_upgraded",
    )

    @property
    def compromises(self) -> List[str]:
        out = [k for k in self.COMPROMISE_KEYS if self.upstream_effects.get(k)]
        if float(self.upstream_effects.get("agent_memory_integrity", 1.0)) < 1.0:
            out.append("agent_memory_degraded")
        if float(self.upstream_effects.get("agent_instruction_fidelity", 1.0)) < 1.0:
            out.append("agent_fidelity_degraded")
        return out

    @property
    def upstream_compromised(self) -> bool:
        return bool(self.compromises)

    @property
    def upstream_succeeded(self) -> bool:
        """Did every non-terminal adjudicated step get through?"""
        return all(
            o.decision in ("ALLOW", "CHALLENGE", "PASS")
            for o in self.outcomes
            if o.action_type != self.terminal_action_type
        )

    @property
    def terminal_action_type(self) -> str:
        return self.outcomes[-1].action_type if self.outcomes else "initiate_payment"

    @property
    def attacker_gain(self) -> Optional[int]:
        """
        Decision severity the upstream attack bought, in steps.

        +1 means the cash-out moved one level in the attacker's favour (BLOCK ->
        CHALLENGE, or CHALLENGE -> ALLOW) because of what happened on the earlier
        surfaces. -1 means the defense caught the composite and scored it *harder*
        than the same payment in isolation.

        Severity is used rather than the risk score because a payment that fails a
        hard control (unverified KYC, unknown beneficiary) never reaches scoring and
        reports risk 0.0 — numerically the lowest risk, semantically the worst
        outcome for the attacker. Comparing those raw scores inverts the result.
        """
        if self.isolated_decision is None:
            return None
        return _severity(self.isolated_decision) - _severity(self.terminal_decision)

    @property
    def risk_delta(self) -> Optional[float]:
        """Risk difference, only meaningful when both sides were actually scored."""
        if self.isolated_risk is None:
            return None
        if self.isolated_risk == 0.0 or self.terminal_risk == 0.0:
            return None  # at least one side hard-blocked pre-scoring
        return round(self.terminal_risk - self.isolated_risk, 4)

    @property
    def evaded(self) -> bool:
        return self.terminal_decision == "ALLOW"

    def summary(self) -> Dict[str, Any]:
        return {
            "chain": self.chain,
            "surfaces": self.surfaces,
            "families": self.families,
            "steps": len(self.outcomes),
            "terminal_decision": self.terminal_decision,
            "terminal_risk": self.terminal_risk,
            "isolated_decision": self.isolated_decision,
            "isolated_risk": self.isolated_risk,
            "attacker_gain": self.attacker_gain,
            "risk_delta": self.risk_delta,
            "evaded": self.evaded,
            "upstream_succeeded": self.upstream_succeeded,
            "intensity": self.intensity,
            "upstream_compromised": self.upstream_compromised,
            "compromises": self.compromises,
            "journey": [
                f"{o.action_type}:{o.decision}" for o in self.outcomes
            ],
        }


class CompositeRunner:
    """Execute composite chains and measure cross-surface uplift."""

    def __init__(
        self,
        sandbox_factory: Callable[[], Any],
        intensity: float = 0.45,
    ):
        """
        `sandbox_factory` returns a fresh PaymentSandbox. `intensity` scales the
        surface mutation space — the default sits near the measured evasion
        boundary, because a chain is only interesting if its upstream steps
        actually succeed.
        """
        self.sandbox_factory = sandbox_factory
        self.intensity = intensity

    #: Intensities swept by `run_best`. A composite only works in the band where
    #: the upstream attack is strong enough to compromise the control but weak
    #: enough to evade it — that band is narrow and differs per surface.
    SWEEP = (0.35, 0.50, 0.60, 0.70, 0.85)

    def run_best(
        self,
        chain: CompositeChain,
        intensities: Optional[tuple] = None,
    ) -> CompositeResult:
        """
        Sweep intensity and return the run that is best for the attacker.

        Ranked by: upstream actually compromised something, then attacker gain,
        then a softer terminal verdict. A chain run at one fixed intensity will
        usually either achieve nothing (too stealthy) or get blocked upstream
        (too loud), and report a misleading "no change".
        """
        best: Optional[CompositeResult] = None
        for intensity in (intensities or self.SWEEP):
            runner = CompositeRunner(self.sandbox_factory, intensity=intensity)
            result = runner.run(chain)
            if best is None or self._rank(result) > self._rank(best):
                best = result
        return best  # type: ignore[return-value]

    @staticmethod
    def _rank(result: CompositeResult) -> tuple:
        return (
            1 if result.upstream_compromised else 0,
            result.attacker_gain or 0,
            -_severity(result.terminal_decision),
        )

    def run(self, chain: CompositeChain, measure_isolated: bool = True) -> CompositeResult:
        from .deepteam.surface_mutator import SurfaceAttackEngine

        engine = SurfaceAttackEngine()
        result = CompositeResult(
            chain=chain.name,
            description=chain.description,
            surfaces=chain.surfaces,
            families=chain.families,
            intensity=self.intensity,
        )

        sandbox = self.sandbox_factory()
        customer_id = f"C_{chain.name[:14]}"
        device_id = f"D_{chain.name[:14]}"
        beneficiary_id = f"B_{chain.name[:14]}"
        # Only reference a beneficiary if the chain actually links one — payment
        # initiation rejects an unknown beneficiary before risk scoring, which
        # would mask the chain's real verdict.
        has_beneficiary = any(s.action_type == "link_beneficiary" for s in chain.steps)

        for step in chain.steps:
            payload: Dict[str, Any] = {
                "customer_id": customer_id,
                "device_id": device_id,
                **step.payload,
            }
            if step.action_type == "link_beneficiary":
                payload.setdefault("beneficiary_id", beneficiary_id)
            if step.action_type == "initiate_payment" and has_beneficiary:
                payload.setdefault("beneficiary_id", beneficiary_id)
            if step.family_id:
                payload.setdefault("attack_family", step.family_id)

            # A network step reads across accounts, so its members have to exist —
            # the engine counts only known customers, and an unregistered member
            # contributes no graph signal.
            for member_id in payload.get("member_customer_ids") or []:
                if sandbox.get_state().get_customer(member_id) is None:
                    sandbox.execute(
                        "register_customer",
                        {
                            "customer_id": member_id,
                            "trust_score": 0.5,
                            "verified": True,
                            "account_age_days": 45,
                        },
                    )
                    sandbox.execute(
                        "register_device",
                        {"device_id": f"D_{member_id}", "customer_id": member_id},
                    )

            technique = resolve_technique(step.action_type)
            if technique is not None and technique.surface != "payment":
                space = engine.space_for(technique.surface)
                if space is not None:
                    payload = engine.apply(space, payload, self.intensity)

            # Snapshot what the upstream surfaces actually achieved, before the
            # cash-out is scored — this is the state the payment inherits.
            if step.action_type == chain.terminal_action:
                from backend.sandbox.rules.feature_context import build_cross_surface_features

                result.upstream_effects = build_cross_surface_features(
                    sandbox.get_state(), customer_id
                )

            observation = sandbox.execute(step.action_type, payload)
            result.outcomes.append(
                StepOutcome(
                    action_type=step.action_type,
                    family_id=step.family_id,
                    surface=getattr(observation, "surface", "payment"),
                    decision=observation.decision,
                    risk_score=float(observation.risk_score or 0.0),
                    reason=observation.reason,
                    control_triggers=list(observation.control_triggers or []),
                    note=step.note,
                )
            )

        if result.outcomes:
            terminal = result.outcomes[-1]
            result.terminal_decision = terminal.decision
            result.terminal_risk = terminal.risk_score

        if measure_isolated:
            iso = self._run_isolated_terminal(chain, customer_id, device_id, beneficiary_id)
            if iso is not None:
                result.isolated_decision, result.isolated_risk = iso

        return result

    def _run_isolated_terminal(
        self,
        chain: CompositeChain,
        customer_id: str,
        device_id: str,
        beneficiary_id: str,
    ) -> Optional[tuple]:
        """
        Run only the terminal step, on fresh state, with the same setup steps.

        This is the control condition: identical payment, no upstream attack.
        """
        terminal = next(
            (s for s in reversed(chain.steps) if s.action_type == chain.terminal_action), None
        )
        if terminal is None:
            return None

        sandbox = self.sandbox_factory()
        has_beneficiary = any(s.action_type == "link_beneficiary" for s in chain.steps)
        for step in chain.steps:
            if step.action_type not in ("register_customer", "register_device", "link_beneficiary"):
                continue
            payload = {"customer_id": customer_id, "device_id": device_id, **step.payload}
            if step.action_type == "link_beneficiary":
                payload.setdefault("beneficiary_id", beneficiary_id)
            sandbox.execute(step.action_type, payload)

        payload = {
            "customer_id": customer_id,
            "device_id": device_id,
            **terminal.payload,
        }
        if has_beneficiary:
            payload.setdefault("beneficiary_id", beneficiary_id)
        observation = sandbox.execute(terminal.action_type, payload)
        return observation.decision, float(observation.risk_score or 0.0)


def chain_by_name(name: str) -> Optional[CompositeChain]:
    return next((c for c in COMPOSITE_CHAINS if c.name == name), None)
