"""Journey-level correlation features for the Risk Engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


# Map journey step display names → engine keys
STEP_TO_ENGINE = {
    "KYC": "kyc",
    "Device": "device",
    "Authentication": "auth",
    "Account": "account",
    "Beneficiary": "beneficiary",
    "Payment Initiation": "payment_init",
    "Gateway/Processor": "gateway",
    "AML/Compliance": "aml",
    "Mule/Cash-out": "mule",
    "Risk": "risk",
    "Authorization": "authz",
    "Settlement": "settlement",
    "Acquirer": "acquirer",
    "AI-Agent Commerce": "agent_commerce",
    "GenAI Context": "agent_commerce",
}


def build_journey_features(
    journey: Optional[List[Any]] = None,
    control_triggers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Derive cross-engine correlation features from the payment journey so far.

    Passed into RuleEngine / RiskEngine so composite rules can span engines.
    """
    steps = journey or []
    triggers = control_triggers or []

    engines_visited: List[str] = []
    flag_engines: Set[str] = set()
    fail_count = 0
    early_block = False
    gateway_flag_count = 0
    aml_flag_count = 0
    total_flags = 0
    statuses: Dict[str, str] = {}

    for idx, step in enumerate(steps):
        if hasattr(step, "step"):
            name = step.step
            result = step.result or {}
        elif isinstance(step, dict):
            name = step.get("step") or step.get("name") or ""
            result = step.get("result") or {}
        else:
            continue

        engine = STEP_TO_ENGINE.get(name, name.lower().replace(" ", "_"))
        if engine not in engines_visited:
            engines_visited.append(engine)

        status = str(result.get("status") or result.get("decision") or "PASS").upper()
        statuses[engine] = status
        if status in ("FAIL", "BLOCK"):
            fail_count += 1
            if idx < max(1, len(steps) - 1):
                early_block = True

        flags = result.get("flags") or result.get("triggered_rules") or []
        if flags:
            flag_engines.add(engine)
            total_flags += len(flags)
            if engine == "gateway":
                gateway_flag_count += len(flags)
            if engine == "aml":
                aml_flag_count += len(flags)

    # Transition risk: more engines with flags → higher correlation score
    engine_transition_risk = min(1.0, len(flag_engines) * 0.12 + fail_count * 0.15)

    return {
        "journey_steps_count": len(steps),
        "journey_engines_visited": engines_visited,
        "journey_engine_count": len(engines_visited),
        "journey_fail_count": fail_count,
        "journey_early_block": early_block,
        "journey_flag_engines": len(flag_engines),
        "journey_flagged_engine_ids": sorted(flag_engines),
        "journey_total_flags": total_flags,
        "journey_gateway_flag_count": gateway_flag_count,
        "journey_aml_flag_count": aml_flag_count,
        "journey_control_trigger_count": len(triggers),
        "engine_transition_risk": round(engine_transition_risk, 4),
        "journey_statuses": statuses,
        # Alias used by composite rules
        "cross_engine_flag_count": len(flag_engines),
    }
