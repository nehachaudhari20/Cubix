"""
Evasion boundary search — the adaptive half of the Red loop.

A fixed ladder of variations tells you *whether* some attack evades. It does not
tell you the most dangerous thing, which is the **strongest attack that still
evades**. That attack is the highest-value training row Blue can get: maximally
aggressive while still scoring below the decision threshold.

The search exploits a property measured on the surfaces: blended risk is close to
monotone in attack intensity, with step-changes where discrete capabilities engage.
So:

  1. ABLATE   drop one capability at a time at full strength. If the attack only
              blocks because of `remote_access_active`, that is worth knowing —
              and the ablated variant may already evade.
  2. BISECT   binary-search intensity for the boundary: the highest intensity
              still returning ALLOW (or CHALLENGE, if `accept_challenge`).
  3. REPORT   return every probe plus the boundary, so Blue trains on the near
              misses rather than only on obvious blocks.

Red never labels its own success here — every probe is adjudicated by the sandbox.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .deepteam.surface_mutator import SurfaceAttackEngine, SurfaceVariation

# Verdicts that mean the attack got through the control surface.
EVADED = ("ALLOW",)
PARTIAL = ("CHALLENGE",)


@dataclass
class Probe:
    """One executed attack attempt and the sandbox's verdict."""

    label: str
    intensity: Optional[float]
    kind: str
    payload: Dict[str, Any]
    decision: str
    risk_score: float
    control_triggers: List[str] = field(default_factory=list)
    control_gaps: Dict[str, Any] = field(default_factory=dict)
    observation: Any = None

    @property
    def evaded(self) -> bool:
        return self.decision in EVADED

    @property
    def partial(self) -> bool:
        return self.decision in PARTIAL


@dataclass
class EvasionResult:
    """Outcome of searching one surface for a family."""

    surface: str
    family_id: Optional[str]
    probes: List[Probe] = field(default_factory=list)
    boundary: Optional[Probe] = None
    boundary_intensity: Optional[float] = None
    blocking_controls: List[str] = field(default_factory=list)
    critical_capability: Optional[str] = None
    executions: int = 0

    @property
    def evaded_count(self) -> int:
        return sum(1 for p in self.probes if p.evaded)

    @property
    def asr(self) -> float:
        if not self.probes:
            return 0.0
        return self.evaded_count / len(self.probes)

    def summary(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "family_id": self.family_id,
            "probes": len(self.probes),
            "evaded": self.evaded_count,
            "asr": round(self.asr, 4),
            "boundary_intensity": self.boundary_intensity,
            "boundary_decision": self.boundary.decision if self.boundary else None,
            "boundary_risk": self.boundary.risk_score if self.boundary else None,
            "critical_capability": self.critical_capability,
            "blocking_controls": self.blocking_controls[:6],
            "executions": self.executions,
        }


def _bisect_steps() -> int:
    try:
        return max(2, min(8, int(os.environ.get("RED_TEAM_BISECT_STEPS", "5"))))
    except ValueError:
        return 5


class EvasionSearch:
    """Search a surface's mutation space for the strongest evading attack."""

    def __init__(
        self,
        engine: Optional[SurfaceAttackEngine] = None,
        accept_challenge: bool = False,
        bisect_steps: Optional[int] = None,
    ):
        self.engine = engine or SurfaceAttackEngine()
        self.accept_challenge = accept_challenge
        self.bisect_steps = bisect_steps if bisect_steps is not None else _bisect_steps()

    def _passes(self, probe: Probe) -> bool:
        return probe.evaded or (self.accept_challenge and probe.partial)

    def search(
        self,
        surface: str,
        base_payload: Dict[str, Any],
        execute: Callable[[Dict[str, Any]], Any],
        family_id: Optional[str] = None,
    ) -> EvasionResult:
        """
        `execute` runs one payload against the sandbox and returns a
        SandboxObservation. It must reset or advance state as the caller intends —
        the search does not manage sandbox lifecycle.
        """
        result = EvasionResult(surface=surface, family_id=family_id)
        space = self.engine.space_for(surface)
        if space is None:
            return result

        def run(variation: SurfaceVariation) -> Probe:
            observation = execute(variation.action_payload)
            probe = Probe(
                label=variation.label,
                intensity=variation.intensity,
                kind=variation.kind,
                payload=variation.action_payload,
                decision=getattr(observation, "decision", "UNKNOWN"),
                risk_score=float(getattr(observation, "risk_score", 0.0) or 0.0),
                control_triggers=list(getattr(observation, "control_triggers", []) or []),
                control_gaps=dict(getattr(observation, "control_gaps", None) or {}),
                observation=observation,
            )
            result.probes.append(probe)
            result.executions += 1
            return probe

        # --- 1. fixed ladder + ablations + categoricals -----------------------
        for variation in self.engine.generate(surface, base_payload):
            run(variation)

        # --- 2. which capability was load-bearing for the block? --------------
        full = [p for p in result.probes if p.kind == "intensity" and (p.intensity or 0) >= 0.90]
        if full and not self._passes(full[0]):
            result.blocking_controls = list(full[0].control_triggers)
            for probe in result.probes:
                if probe.kind == "ablation" and self._passes(probe):
                    result.critical_capability = probe.payload.get("_ablated") or (
                        probe.label.replace("ablate_", "")
                    )
                    break

        # --- 3. bisect the intensity axis for the boundary --------------------
        boundary = self._bisect(surface, base_payload, run)
        if boundary is not None:
            result.boundary = boundary
            result.boundary_intensity = boundary.intensity

        return result

    def _bisect(
        self,
        surface: str,
        base_payload: Dict[str, Any],
        run: Callable[[SurfaceVariation], Probe],
    ) -> Optional[Probe]:
        """
        Binary search for the highest intensity that still gets through.

        `low` is known-passing, `high` known-blocking. If the lowest intensity
        already blocks there is no boundary to find (the surface is fully closed
        for this family); if the highest still passes, the surface is fully open.
        """
        space = self.engine.space_for(surface)
        if space is None:
            return None

        def probe_at(intensity: float) -> Probe:
            payload = self.engine.apply(space, base_payload, intensity)
            return run(
                SurfaceVariation(
                    variation_id=f"bisect_{intensity:.3f}",
                    label=f"bisect_{intensity:.3f}",
                    action_payload=payload,
                    intensity=intensity,
                    kind="bisect",
                )
            )

        low, high = 0.05, 0.98
        low_probe = probe_at(low)
        if not self._passes(low_probe):
            return None  # closed even at minimum strength
        high_probe = probe_at(high)
        if self._passes(high_probe):
            return high_probe  # open even at maximum strength

        best = low_probe
        for _ in range(self.bisect_steps):
            mid = round((low + high) / 2, 4)
            probe = probe_at(mid)
            if self._passes(probe):
                best, low = probe, mid
            else:
                high = mid
        return best


def search_surface_family(
    *,
    surface: str,
    family_id: Optional[str],
    base_payload: Dict[str, Any],
    execute: Callable[[Dict[str, Any]], Any],
    accept_challenge: bool = False,
) -> EvasionResult:
    """Convenience entry point for one (surface, family) pair."""
    return EvasionSearch(accept_challenge=accept_challenge).search(
        surface, base_payload, execute, family_id=family_id
    )
