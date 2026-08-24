"""
KB Campaign Builder — dynamic attack plan synthesis from all three KB JSON files.

Reads attack_families.json, attack_signals.json, lifecycle_stages.json and produces
executable sandbox action plans without static CAMPAIGN_TEMPLATES.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .schemas import AttackPlan, Hypothesis, PlanStep


# Families whose simulation_type is purely agentic (no payment sandbox actions yet)
PURE_AGENTIC = {"agentic"}

# Keyword buckets used to classify a family into a sandbox campaign shape
PATTERN_KEYWORDS: Dict[str, List[str]] = {
    "mule": ["mule", "cash-out", "cash out", "beneficiary", "layering tier", "recruitment"],
    "merchant": ["merchant", "mcc", "acquirer", "acq-", "kyb", "misrepresentation"],
    "identity": ["synthetic identity", "sif-", "identity fabrication", "document fabrication", "kyc"],
    "aml": ["aml", "structuring", "smurfing", "money laundering", "layering"],
    "velocity": ["velocity", "threshold", "low-and-slow", "authorization feature", "splitting"],
    "account": ["account creation", "onboarding", "open account", "account farming"],
    "auth": ["authentication", "account takeover", "ato-", "credential"],
}

# Map sandbox action types to typical lifecycle stage keywords
STAGE_ACTION_HINTS: Dict[str, List[str]] = {
    "register_customer": ["identity", "kyc", "account creation", "onboarding"],
    "register_device": ["device", "authentication"],
    "open_account": ["account creation", "onboarding"],
    "onboard_merchant": ["merchant", "acquirer", "acq"],
    "link_beneficiary": ["beneficiary", "mule", "cash-out"],
    "initiate_payment": ["payment", "authorization", "settlement", "gateway"],
}

# Signal name / detection_method fragments → payload parameter hints
SIGNAL_PAYLOAD_RULES: List[Tuple[str, Dict[str, Any]]] = [
    (r"threshold|just below|999", {"amount": 9999}),
    (r"high.?amount|high.?value|large transfer", {"amount": 35000}),
    (r"medium|moderate", {"amount": 8000}),
    (r"low.?value|small|probe", {"amount": 2500}),
    (r"new beneficiary|fresh beneficiary", {"needs_beneficiary": True, "amount": 35000}),
    (r"mcc|merchant misrepresentation|misrepresentation", {"needs_merchant": True, "mcc": "7995", "declared_mcc": "5411", "amount": 45000}),
    (r"synthetic|low trust|trust score", {"trust_score": 0.32, "pan": "SYN0009999"}),
    (r"velocity|burst|repeat|multiple transaction", {"velocity_burst": True}),
    (r"structuring|smurfing|split", {"structuring": True}),
    (r"account|balance", {"needs_account": True, "balance": 75000}),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _family_text_blob(family: Dict[str, Any]) -> str:
    parts = [
        family.get("name") or "",
        family.get("lifecycle_stage") or "",
        family.get("attack_id") or "",
        " ".join(family.get("attack_flow") or []),
        " ".join(family.get("controls_targeted") or []),
        " ".join(family.get("variants") or []),
        " ".join(family.get("prerequisites") or []),
    ]
    for sig in family.get("detection_signals") or []:
        parts.append(sig.get("name") or "")
        parts.append(sig.get("detection_method") or "")
    return _normalize(" ".join(parts))


def is_simulatable(family: Dict[str, Any]) -> bool:
    """True if family can be exercised in the current payment sandbox."""
    sim_type = _normalize(family.get("simulation_type") or "")
    if sim_type in PURE_AGENTIC:
        return False
    if "algorithmic" in sim_type or "hybrid" in sim_type:
        return True
    # Fallback: payment-related lifecycle stages
    stage = _normalize(family.get("lifecycle_stage") or "")
    payment_stages = (
        "payment", "authorization", "identity", "kyc", "mule", "merchant",
        "beneficiary", "account", "authentication", "aml", "cash-out", "gateway",
    )
    return any(k in stage for k in payment_stages)


def classify_family(family: Dict[str, Any]) -> str:
    """Classify family into a sandbox campaign shape."""
    blob = _family_text_blob(family)
    scores: Dict[str, int] = {k: 0 for k in PATTERN_KEYWORDS}
    for pattern, keywords in PATTERN_KEYWORDS.items():
        for kw in keywords:
            if kw in blob:
                scores[pattern] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "payment_probe"


def derive_payload_hints(family: Dict[str, Any], global_signals: List[Dict]) -> Dict[str, Any]:
    """Merge family detection_signals + matched global signals into payload hints."""
    hints: Dict[str, Any] = {}
    signal_texts: List[str] = []

    for sig in family.get("detection_signals") or []:
        signal_texts.append(_normalize(sig.get("name") or ""))
        signal_texts.append(_normalize(sig.get("detection_method") or ""))

    family_id = family.get("attack_id")
    for gs in global_signals:
        # Global signals file has no family_id — match by name overlap with family signals
        gs_name = _normalize(gs.get("signal_name") or gs.get("name") or "")
        if any(gs_name in ft or ft in gs_name for ft in signal_texts if ft):
            signal_texts.append(gs_name)
            signal_texts.append(_normalize(gs.get("detection_method") or ""))

    combined = " ".join(signal_texts)
    for pattern, params in SIGNAL_PAYLOAD_RULES:
        if re.search(pattern, combined, re.I):
            hints.update(params)

    # Pattern-based defaults when signals are sparse
    pattern = classify_family(family)
    defaults = {
        "mule": {"needs_beneficiary": True, "amount": 35000},
        "merchant": {"needs_merchant": True, "mcc": "7995", "declared_mcc": "5411", "amount": 45000},
        "identity": {"trust_score": 0.32, "pan": "SYN0009999", "amount": 15000},
        "aml": {"structuring": True, "amount": 9500},
        "velocity": {"velocity_burst": True},
        "account": {"needs_account": True, "balance": 75000, "amount": 12000},
        "auth": {"amount": 18000},
        "payment_probe": {"amount": 10000},
    }
    for k, v in defaults.get(pattern, {}).items():
        hints.setdefault(k, v)

    # Prevent cross-pattern signal bleed (e.g. velocity family picking up MCC hints)
    if pattern != "merchant":
        hints.pop("needs_merchant", None)
        hints.pop("mcc", None)
        hints.pop("declared_mcc", None)
    if pattern != "mule":
        hints.pop("needs_beneficiary", None)
    else:
        hints.pop("needs_account", None)
        hints.pop("velocity_burst", None)
    if pattern != "velocity":
        hints.pop("velocity_burst", None)
    if pattern != "aml":
        hints.pop("structuring", None)
    if pattern not in ("account", "aml"):
        hints.pop("needs_account", None)

    return hints


def get_stage_controls(stages: List[Dict], stage_name: str) -> List[str]:
    """Lookup controls for a lifecycle stage from lifecycle_stages.json."""
    target = _normalize(stage_name)
    for stage in stages:
        name = _normalize(stage.get("stage_name") or stage.get("name") or stage.get("stage") or "")
        if target in name or name in target:
            return stage.get("controls") or []
    return []


def pick_target_control(family: Dict[str, Any], stages: List[Dict], action_type: str) -> str:
    """Pick the most relevant KB control for a plan step."""
    family_controls = family.get("controls_targeted") or []
    if family_controls:
        if action_type == "initiate_payment":
            for c in family_controls:
                cl = c.lower()
                if any(k in cl for k in ("velocity", "risk", "amount", "authorization")):
                    return c
            return family_controls[0]
        return family_controls[0]

    stage_controls = get_stage_controls(stages, family.get("lifecycle_stage") or "")
    if stage_controls:
        return stage_controls[0]

    return {
        "register_customer": "Identity/KYC",
        "register_device": "Device",
        "open_account": "Account Creation",
        "onboard_merchant": "Merchant",
        "link_beneficiary": "Beneficiary",
        "initiate_payment": "Authorization",
    }.get(action_type, "Risk")


def build_hypothesis_from_family(family: Dict[str, Any]) -> Hypothesis:
    """Create a Threat Hunter hypothesis directly from a KB family record."""
    attack_flow = family.get("attack_flow") or []
    flow_summary = " → ".join(attack_flow[:5]) if attack_flow else family.get("name", "")

    return Hypothesis(
        name=family.get("name") or family.get("attack_id"),
        primary_family=family.get("attack_id"),
        composite_families=[],
        target_stages=[family.get("lifecycle_stage") or "Payment Initiation"],
        novelty_score=0.7 if "hybrid" in _normalize(family.get("simulation_type") or "") else 0.6,
        success_probability=0.45,
        prerequisites=(family.get("prerequisites") or ["Registered customer"])[:4],
        attack_flow_summary=flow_summary,
        reasoning=(
            f"KB family {family.get('attack_id')} targets stage "
            f"'{family.get('lifecycle_stage')}' with pattern '{classify_family(family)}'."
        ),
        suggested_variant=(family.get("variants") or ["default"])[0],
    )


def _payment_steps(
    hints: Dict[str, Any],
    family: Dict[str, Any],
    stages: List[Dict],
    start_step: int,
) -> Tuple[List[PlanStep], int]:
    """Build payment step(s) based on payload hints."""
    steps: List[PlanStep] = []
    step_num = start_step

    if hints.get("structuring"):
        amounts = [9500, 9800, 9200, 9900]
        for i, amt in enumerate(amounts):
            steps.append(PlanStep(
                step=step_num,
                action_type="initiate_payment",
                action=f"Structured payment {i + 1} (AML probe)",
                target_control=pick_target_control(family, stages, "initiate_payment"),
                payload_template={"amount": amt, "structuring_index": i},
                expected_outcome="ALLOW",
                rationale=f"Probe AML structuring signal at ₹{amt}",
            ))
            step_num += 1
        return steps, step_num

    if hints.get("velocity_burst"):
        amounts = [2000, 5000, 3000, 3000, 3000, 8000]
        labels = ["Trust-build low", "Medium probe", "Velocity repeat"] * 2 + ["Burst payment"]
        for i, amt in enumerate(amounts):
            steps.append(PlanStep(
                step=step_num,
                action_type="initiate_payment",
                action=labels[i] if i < len(labels) else f"Payment {i + 1}",
                target_control=pick_target_control(family, stages, "initiate_payment"),
                payload_template={"amount": amt, "velocity_index": i},
                expected_outcome="ALLOW",
                rationale=f"Velocity evasion probe step {i + 1}",
            ))
            step_num += 1
        return steps, step_num

    amount = hints.get("amount", 10000)
    steps.append(PlanStep(
        step=step_num,
        action_type="initiate_payment",
        action=f"Payment probe (₹{amount})",
        target_control=pick_target_control(family, stages, "initiate_payment"),
        payload_template={"amount": amount},
        expected_outcome="ALLOW",
        rationale="Primary payment probe derived from KB signals",
    ))
    step_num += 1
    return steps, step_num


def build_plan_from_family(
    family: Dict[str, Any],
    stages: List[Dict],
    global_signals: List[Dict],
    hypothesis: Optional[Hypothesis] = None,
) -> AttackPlan:
    """Synthesize an AttackPlan from KB family + stages + signals."""
    if hypothesis is None:
        hypothesis = build_hypothesis_from_family(family)

    hints = derive_payload_hints(family, global_signals)
    pattern = classify_family(family)
    steps: List[PlanStep] = []
    step_num = 1

    # Setup steps common to all campaigns
    trust = float(hints.get("trust_score", 0.65))
    steps.append(PlanStep(
        step=step_num,
        action_type="register_customer",
        action=f"Register customer for {family.get('attack_id')}",
        target_control=pick_target_control(family, stages, "register_customer"),
        payload_template={
            "trust_score": trust,
            "pan": hints.get("pan", "SYN0000001"),
            "verified": trust >= 0.5,
        },
        expected_outcome="PASS",
        rationale=f"Setup payer per KB prerequisites: {(family.get('prerequisites') or [''])[0][:80]}",
    ))
    step_num += 1

    steps.append(PlanStep(
        step=step_num,
        action_type="register_device",
        action="Register device fingerprint",
        target_control=pick_target_control(family, stages, "register_device"),
        payload_template={},
        expected_outcome="PASS",
        rationale="Device registration required before payment lifecycle",
    ))
    step_num += 1

    if hints.get("needs_account") or pattern == "account":
        steps.append(PlanStep(
            step=step_num,
            action_type="open_account",
            action="Open synthetic account",
            target_control=pick_target_control(family, stages, "open_account"),
            payload_template={"balance": hints.get("balance", 75000)},
            expected_outcome="PASS",
            rationale="KB pattern requires account provisioning",
        ))
        step_num += 1

    if hints.get("needs_merchant") or pattern == "merchant":
        steps.append(PlanStep(
            step=step_num,
            action_type="onboard_merchant",
            action="Onboard merchant (KB MCC probe)",
            target_control=pick_target_control(family, stages, "onboard_merchant"),
            payload_template={
                "mcc": hints.get("mcc", "7995"),
                "declared_mcc": hints.get("declared_mcc", "5411"),
                "risk_score": 0.35,
            },
            expected_outcome="PASS",
            rationale="Merchant onboarding per KB merchant/MCC signals",
        ))
        step_num += 1

    if hints.get("needs_beneficiary") or pattern == "mule":
        steps.append(PlanStep(
            step=step_num,
            action_type="link_beneficiary",
            action="Link new beneficiary (mule probe)",
            target_control=pick_target_control(family, stages, "link_beneficiary"),
            payload_template={"risk_score": 0.25},
            expected_outcome="PASS",
            rationale="Beneficiary link per KB mule/cash-out attack flow",
        ))
        step_num += 1

    payment_steps, step_num = _payment_steps(hints, family, stages, step_num)
    steps.extend(payment_steps)

    variant = hypothesis.suggested_variant or (family.get("variants") or ["default"])[0]
    stage_name = family.get("lifecycle_stage") or "Payment Initiation"

    return AttackPlan(
        campaign_name=family.get("name") or hypothesis.name,
        objective=(
            f"Simulate {family.get('attack_id')} ({pattern}) against "
            f"stage '{stage_name}' using {len(steps)} sandbox actions"
        ),
        target_stages=[stage_name],
        primary_family=family.get("attack_id"),
        selected_variant=variant,
        steps=steps,
        success_criteria="Final payment returns ALLOW or exposes target control triggers",
        estimated_complexity="high" if len(steps) > 6 else "medium" if len(steps) > 3 else "low",
        reasoning=hypothesis.reasoning,
    )


def match_triggers_to_kb_signals(
    triggers: List[str],
    family: Dict[str, Any],
    global_signals: List[Dict],
) -> List[str]:
    """Map sandbox control_triggers back to KB signal names."""
    matched: List[str] = []
    trigger_blob = _normalize(" ".join(triggers))

    for sig in family.get("detection_signals") or []:
        name = sig.get("name") or ""
        method = sig.get("detection_method") or ""
        sig_blob = _normalize(f"{name} {method}")
        if any(tok in trigger_blob for tok in sig_blob.split() if len(tok) > 4):
            matched.append(name)
        elif any(tok in sig_blob for tok in trigger_blob.split() if len(tok) > 4):
            matched.append(name)

    for gs in global_signals:
        gs_name = gs.get("signal_name") or gs.get("name") or ""
        gs_method = gs.get("detection_method") or ""
        gs_blob = _normalize(f"{gs_name} {gs_method}")
        if any(tok in trigger_blob for tok in gs_blob.split() if len(tok) > 5):
            if gs_name not in matched:
                matched.append(gs_name)

    return matched[:5]
