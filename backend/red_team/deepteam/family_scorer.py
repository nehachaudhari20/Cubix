"""Score KB attack families for CVSS-style prioritization."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from backend.red_team.kb_campaign_builder import classify_family, derive_payload_hints
from backend.red_team.schemas import MemoryEntry

from .cvss_scorer import score_family
from .schemas import AttackCandidate, JailbreakStrategy


def estimate_potential_amount(family: Dict[str, Any], global_signals: List[Dict]) -> float:
    hints = derive_payload_hints(family, global_signals)
    amount = hints.get("amount")
    if amount is not None:
        return float(amount)
    pattern = classify_family(family)
    defaults = {
        "mule": 35000.0,
        "merchant": 45000.0,
        "aml": 9500.0,
        "velocity": 8000.0,
        "identity": 15000.0,
    }
    return defaults.get(pattern, 10000.0)


def estimate_step_count(family: Dict[str, Any]) -> int:
    flow = family.get("attack_flow") or []
    if flow:
        return max(1, min(len(flow), 8))
    pattern = classify_family(family)
    pattern_steps = {
        "mule": 4,
        "merchant": 4,
        "velocity": 3,
        "aml": 5,
        "identity": 3,
        "account": 4,
        "auth": 3,
    }
    return pattern_steps.get(pattern, 2)


def estimate_bypass_probability(
    family: Dict[str, Any],
    tested_ids: Set[str],
    memories: Optional[List[MemoryEntry]] = None,
) -> float:
    attack_id = family.get("attack_id") or ""
    pattern = classify_family(family)
    probability = 0.35

    control_count = len(family.get("targeted_control_ids") or [])
    probability -= min(control_count * 0.02, 0.15)

    genai = (family.get("genai_classification") or "").lower()
    if genai in ("genai_load_bearing", "genai_amplified"):
        probability += 0.08

    if attack_id in tested_ids:
        probability -= 0.12

    for memory in memories or []:
        conditions = memory.applicable_conditions or {}
        if conditions.get("primary_family") == attack_id:
            if conditions.get("outcome") == "success":
                probability += 0.15
            elif conditions.get("outcome") == "failure":
                probability -= 0.08
        elif pattern in (memory.attack_attempted or "").lower():
            if memory.response == "success":
                probability += 0.05

    return max(0.05, min(probability, 0.85))


def build_attack_candidate(
    family: Dict[str, Any],
    global_signals: List[Dict],
    *,
    tested_ids: Optional[Set[str]] = None,
    memories: Optional[List[MemoryEntry]] = None,
    strategy: JailbreakStrategy = JailbreakStrategy.LINEAR,
) -> AttackCandidate:
    tested = tested_ids or set()
    amount = estimate_potential_amount(family, global_signals)
    steps = estimate_step_count(family)
    bypass = estimate_bypass_probability(family, tested, memories)
    return score_family(
        family.get("attack_id", "UNKNOWN"),
        family.get("name", "Unknown"),
        potential_amount=amount,
        step_count=steps,
        bypass_probability=bypass,
        strategy=strategy,
        plan_objective=f"Probe {classify_family(family)} pattern at {family.get('lifecycle_stage')}",
    )


def prioritize_families(
    families: List[Dict[str, Any]],
    global_signals: List[Dict],
    *,
    tested_ids: Optional[Set[str]] = None,
    memories: Optional[List[MemoryEntry]] = None,
    limit: int = 10,
) -> List[AttackCandidate]:
    tested = tested_ids or set()
    candidates = [
        build_attack_candidate(
            family,
            global_signals,
            tested_ids=tested,
            memories=memories,
        )
        for family in families
        if family.get("attack_id") not in tested
    ]
    candidates.sort(key=lambda item: item.cvss.composite, reverse=True)
    return candidates[:limit]
