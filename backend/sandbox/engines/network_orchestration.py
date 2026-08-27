"""
Network Orchestration Engine — STG-0048 (Cross-Stage Network).

Adjudicates the `network` surface: AI-coordinated fraud rings, multi-stage
campaigns, and social engineering aimed at the AML review process itself.

This is the only surface that reads across *other* accounts, so it is where the
graph signals Blue trains on actually get produced.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..state import SandboxState


class NetworkOrchestrationEngine:
    """Cross-account coordination and ring-structure checks."""

    def __init__(self, state: SandboxState):
        self.state = state

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        genai = payload.get("genai_features") or {}
        member_ids = [str(m) for m in (payload.get("member_customer_ids") or [])]
        shared_beneficiary = payload.get("shared_beneficiary_id")

        known_members = [m for m in member_ids if self.state.get_customer(m)]
        ring_size = len(known_members)

        if ring_size >= 3:
            flags.append("net_coordinated_account_cluster")
        if ring_size >= 8:
            flags.append("net_large_ring_structure")

        # --- shared beneficiary fan-in (real graph read) --------------------------
        distinct_payers = 0
        if shared_beneficiary:
            distinct_payers = self.state.count_distinct_payers_to_beneficiary(shared_beneficiary)
            if distinct_payers >= 3:
                flags.append("net_shared_beneficiary_fan_in")

        # --- shared device across members ----------------------------------------
        device_owners: Dict[str, int] = {}
        for device in self.state.devices.values():
            device_owners[device.device_id] = device_owners.get(device.device_id, 0) + 1
        shared_devices = [d for d, n in device_owners.items() if n > 1]
        if shared_devices:
            flags.append("net_shared_device_across_accounts")

        # --- coordination signals -------------------------------------------------
        if float(genai.get("fraud_ring_coordination_score") or 0) >= 0.60:
            flags.append("net_ai_ring_coordination")
        if float(genai.get("network_orchestration_score") or 0) >= 0.60:
            flags.append("net_orchestration_indicators")
        if float(genai.get("multi_stage_coordination_score") or 0) >= 0.60:
            flags.append("net_multi_stage_coordination")
        if float(genai.get("mule_recruitment_score") or 0) >= 0.60:
            flags.append("net_mule_recruitment_activity")

        # --- AML review-process manipulation --------------------------------------
        if payload.get("aml_narrative_submitted"):
            flags.append("net_aml_narrative_submitted")
            if float(genai.get("aml_model_poisoning_score") or 0) >= 0.55:
                flags.append("net_aml_process_manipulation")
        if float(genai.get("label_flipping_risk") or 0) >= 0.55:
            flags.append("net_label_flipping_attempt")

        risk = min(1.0, 0.15 * len(flags) + min(ring_size, 10) * 0.02)
        return {
            "status": "PASS",
            "stage": "STG-0048",
            "engine": "network",
            "flags": flags,
            "network_risk": round(risk, 4),
            "ring_size": ring_size,
            "graph_cluster_size": max(ring_size, 1),
            "beneficiary_distinct_payer_count": distinct_payers,
            "is_shared_beneficiary": bool(distinct_payers >= 2),
            "shared_device_customer_count": len(shared_devices),
        }
