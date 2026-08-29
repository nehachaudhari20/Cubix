"""Simulation Safety Gateway — ensures all Red Team activity remains synthetic, bounded, auditable, and non-deployable."""

from .policy_engine import SimulationPolicyEngine, PolicyDecision

__all__ = ["SimulationPolicyEngine", "PolicyDecision"]
