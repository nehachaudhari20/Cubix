"""
Agent Trust Engine — STG-0001 / STG-0003 (AI Agent Commerce).

Adjudicates the `agent` surface: prompt injection, agent impersonation, memory
poisoning, agent-to-agent manipulation, agentic payment-protocol abuse.

State is durable on purpose. Memory poisoning that lands degrades the agent's
`memory_integrity` permanently, so a second attempt against the same agent starts
from a weaker position — the same way a real poisoned context does.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..state import SandboxState


class AgentTrustEngine:
    """Agent identity, mandate scope, and context integrity checks."""

    def __init__(self, state: SandboxState):
        self.state = state

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        customer_id = payload.get("customer_id") or ""
        agent_id = payload.get("agent_id") or f"agent_{customer_id or 'anon'}"
        genai = payload.get("genai_features") or {}

        agent = self.state.get_or_create_agent(
            agent_id,
            customer_id,
            mandate_scope=list(payload.get("mandate_scope") or ["read"]),
            tool_scope=list(payload.get("tool_scope") or ["search"]),
            spend_limit=float(payload.get("spend_limit", 25000.0)),
            is_verified=bool(payload.get("agent_verified", True)),
        )

        # --- instruction fidelity (prompt injection / goal hacking) -----------
        injection = float(genai.get("prompt_injection_risk") or 0)
        goal_hack = float(genai.get("goal_hacking_score") or 0)
        hidden = float(genai.get("hidden_instruction_density") or 0)
        if injection >= 0.60 or hidden >= 0.60:
            flags.append("agent_instruction_injection")
            agent.instruction_fidelity = max(0.0, agent.instruction_fidelity - 0.25)
        if goal_hack >= 0.60:
            flags.append("agent_goal_divergence")

        # --- agent identity (impersonation) -----------------------------------
        if not agent.is_verified:
            flags.append("agent_unverified_identity")
        if payload.get("counterparty_agent_unverified"):
            flags.append("agent_counterparty_unverified")

        # --- memory / context integrity ---------------------------------------
        poisoning = float(genai.get("memory_poisoning_score") or 0)
        context_poison = float(genai.get("context_poisoning_score") or 0)
        if poisoning >= 0.55 or context_poison >= 0.55:
            flags.append("agent_memory_poisoning")
            agent.poisoning_attempts += 1
            agent.memory_integrity = max(0.0, agent.memory_integrity - 0.30)
        if agent.memory_integrity < 0.60:
            flags.append("agent_memory_integrity_degraded")

        # --- tool / mandate scope ---------------------------------------------
        requested_tools = list(payload.get("requested_tools") or [])
        out_of_scope = [t for t in requested_tools if t not in agent.tool_scope]
        if out_of_scope:
            flags.append("agent_tool_scope_violation")
        tool_abuse = float(genai.get("agentic_tool_abuse_score") or 0)
        if tool_abuse >= 0.60 or float(genai.get("unauthorized_tool_call_risk") or 0) >= 0.60:
            flags.append("agent_unauthorized_tool_call")

        requested_amount = float(payload.get("requested_amount") or 0)
        if requested_amount > agent.spend_limit:
            flags.append("agent_mandate_limit_exceeded")

        # --- A2A channel -------------------------------------------------------
        if payload.get("a2a_channel") and not payload.get("a2a_channel_authenticated", False):
            flags.append("agent_a2a_channel_unauthenticated")

        risk = min(1.0, 0.18 * len(flags) + (1.0 - agent.memory_integrity) * 0.20)
        status = "FAIL" if "agent_mandate_limit_exceeded" in flags and requested_amount > 0 else "PASS"

        return {
            "status": status,
            "stage": "STG-0001",
            "engine": "agent",
            "flags": flags,
            "agent_risk": round(risk, 4),
            "agent_id": agent.agent_id,
            "memory_integrity": round(agent.memory_integrity, 4),
            "instruction_fidelity": round(agent.instruction_fidelity, 4),
            "session_count": agent.session_count,
            "poisoning_attempts": agent.poisoning_attempts,
            "out_of_scope_tools": out_of_scope,
        }
