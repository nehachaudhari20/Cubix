"""
Attack Planner Agent — KB + composite multi-family plans + DeepTeam jailbreaks.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Set

from ..schemas import Hypothesis, AttackPlan, PlanStep
from ..agent_helpers import OfflineKnowledge, get_llm, use_llm
from ..kb_campaign_builder import (
    build_plan_from_family,
    classify_family,
    derive_payload_hints,
)
from ..composite_intel import is_genai_load_bearing
from ..deepteam.jailbreak_planner import JailbreakPlanner
from ..deepteam.strategy_config import resolve_jailbreak_strategy
from ..deepteam.schemas import JailbreakStrategy


# Prefer setup / GenAI before payment when merging composites
_ACTION_PRIORITY = {
    "simulate_genai_context": 0,
    "register_customer": 1,
    "register_device": 2,
    "authenticate": 3,
    "verify_kyc": 4,
    "open_account": 5,
    "onboard_merchant": 6,
    "link_beneficiary": 7,
    "initiate_payment": 8,
}


class AttackPlanner:
    """Builds step-by-step campaigns from KB data and DeepTeam jailbreak planners."""

    def __init__(self, model_name: str = None):
        self.kb = OfflineKnowledge()
        self.jailbreak_planner = JailbreakPlanner()

    def plan(self, hypothesis: Hypothesis) -> AttackPlan:
        branches = self.plan_branches(hypothesis)
        return branches[0]

    def plan_branches(self, hypothesis: Hypothesis) -> List[AttackPlan]:
        family = self.kb.get_family(hypothesis.primary_family)
        if not family:
            raise ValueError(f"Family {hypothesis.primary_family} not found in KB")

        # Composite multi-family campaigns take precedence
        if hypothesis.composite_families:
            composite_plan = self._plan_composite(hypothesis)
            if composite_plan:
                return [composite_plan]

        strategy = resolve_jailbreak_strategy(hypothesis)

        if strategy is None:
            if get_llm() and use_llm():
                llm_plan = self._plan_with_llm(hypothesis, family)
                if llm_plan:
                    llm_plan = self._finalize_llm_plan(llm_plan, family, hypothesis)
                    llm_plan.jailbreak_strategy = "kb+llm"
                    return [llm_plan]
            kb_plan = build_plan_from_family(
                family=family,
                stages=self.kb.stages,
                global_signals=self.kb.signals,
                hypothesis=hypothesis,
            )
            kb_plan.jailbreak_strategy = "kb"
            return [kb_plan]

        plans = self.jailbreak_planner.plan(family, strategy)
        enriched = [self._enrich_with_kb_hints(plan, family) for plan in plans]
        for plan in enriched:
            plan.jailbreak_strategy = strategy.value
        return enriched

    def plan_from_family_id(
        self,
        family_id: str,
        strategy: Optional[JailbreakStrategy] = None,
    ) -> AttackPlan:
        """Direct KB family -> plan (continuous runner)."""
        hypothesis = Hypothesis(
            name=family_id,
            primary_family=family_id,
            target_stages=["Payment Initiation"],
            novelty_score=0.6,
            success_probability=0.45,
            prerequisites=["Registered customer"],
            attack_flow_summary=family_id,
            reasoning=f"Direct plan for {family_id}",
            jailbreak_strategy=strategy.value if strategy else None,
        )
        return self.plan(hypothesis)

    def _resolve_composite_families(self, hypothesis: Hypothesis) -> List[dict]:
        ids = [hypothesis.primary_family, *(hypothesis.composite_families or [])]
        families: List[dict] = []
        seen: Set[str] = set()
        for fid in ids:
            if not fid or fid in seen:
                continue
            fam = self.kb.get_family(fid)
            if fam:
                families.append(fam)
                seen.add(fid)
        return families

    def _plan_composite(self, hypothesis: Hypothesis) -> Optional[AttackPlan]:
        """Merge KB template plans from primary + composite families into one campaign."""
        families = self._resolve_composite_families(hypothesis)
        if len(families) < 2:
            return None

        member_plans: List[AttackPlan] = []
        for fam in families:
            member_h = hypothesis.model_copy(
                update={
                    "primary_family": fam.get("attack_id"),
                    "composite_families": [],
                    "name": fam.get("name") or fam.get("attack_id"),
                }
            )
            plan = build_plan_from_family(
                family=fam,
                stages=self.kb.stages,
                global_signals=self.kb.signals,
                hypothesis=member_h,
            )
            member_plans.append(plan)

        merged_steps = self._merge_composite_steps(member_plans, families)
        if not merged_steps:
            return None

        # Ensure GenAI context appears early when any member is GenAI load-bearing
        if any(is_genai_load_bearing(f) for f in families):
            merged_steps = self._ensure_genai_step(merged_steps, families)

        stages: List[str] = []
        for plan in member_plans:
            stages.extend(plan.target_stages or [])
        stages.extend(hypothesis.target_stages or [])
        stages = list(dict.fromkeys(stages))
        family_ids = [f.get("attack_id") for f in families]
        return AttackPlan(
            campaign_name=hypothesis.name or f"Composite {'+'.join(family_ids)}",
            objective=(
                f"Composite kill-chain across {', '.join(family_ids)}: "
                f"{hypothesis.attack_flow_summary[:240]}"
            ),
            target_stages=stages or ["Payment Initiation"],
            primary_family=hypothesis.primary_family,
            selected_variant=hypothesis.suggested_variant
            or (families[0].get("variants") or ["default"])[0],
            steps=merged_steps,
            success_criteria=(
                "Complete multi-family setup + GenAI context (if applicable) + "
                "payment probes that exercise combined control surfaces"
            ),
            estimated_complexity="high",
            reasoning=(
                f"{hypothesis.reasoning} "
                f"Merged {len(member_plans)} KB template plans → {len(merged_steps)} steps."
            ),
            jailbreak_strategy="composite",
            entry_point="cross_stage",
        )

    def _merge_composite_steps(
        self,
        member_plans: List[AttackPlan],
        families: List[dict],
    ) -> List[PlanStep]:
        """Deduplicate setup actions; keep payment probes from each family."""
        setup_seen: Set[str] = set()
        setup_steps: List[PlanStep] = []
        payment_steps: List[PlanStep] = []
        genai_steps: List[PlanStep] = []

        for plan, fam in zip(member_plans, families):
            fid = fam.get("attack_id") or plan.primary_family
            for step in plan.steps:
                tagged = self._tag_step(step, fid)
                at = tagged.action_type

                if at == "simulate_genai_context":
                    if "simulate_genai_context" not in setup_seen:
                        genai_steps.append(tagged)
                        setup_seen.add("simulate_genai_context")
                    continue

                if at == "initiate_payment":
                    payment_steps.append(tagged)
                    continue

                # One of each setup action type (first family wins, annotated)
                if at not in setup_seen:
                    setup_steps.append(tagged)
                    setup_seen.add(at)
                elif at == "onboard_merchant" and classify_family(fam) == "merchant":
                    # Prefer merchant-pattern family's onboard step
                    setup_steps = [s for s in setup_steps if s.action_type != "onboard_merchant"]
                    setup_steps.append(tagged)

        ordered = sorted(
            genai_steps + setup_steps,
            key=lambda s: _ACTION_PRIORITY.get(s.action_type, 50),
        )
        # Cap payment probes but keep diversity across families
        capped_payments = payment_steps[:6] if len(payment_steps) > 6 else payment_steps
        combined = ordered + capped_payments

        renumbered: List[PlanStep] = []
        for i, step in enumerate(combined, start=1):
            renumbered.append(step.model_copy(update={"step": i}))
        return renumbered

    @staticmethod
    def _tag_step(step: PlanStep, family_id: str) -> PlanStep:
        tpl = dict(step.payload_template or {})
        tpl.setdefault("attack_family", family_id)
        tpl.setdefault("composite_source", family_id)
        action = step.action
        if family_id and family_id not in action:
            action = f"{action} [{family_id}]"
        return step.model_copy(update={"payload_template": tpl, "action": action})

    def _ensure_genai_step(
        self,
        steps: List[PlanStep],
        families: List[dict],
    ) -> List[PlanStep]:
        if any(s.action_type == "simulate_genai_context" for s in steps):
            return steps

        genai_fam = next((f for f in families if is_genai_load_bearing(f)), families[0])
        caps = (genai_fam.get("genai") or {}).get("capability_ids") or []
        genai_step = PlanStep(
            step=1,
            action_type="simulate_genai_context",
            action=f"Simulate GenAI attack context [{genai_fam.get('attack_id')}]",
            target_control="GenAI / Agent Controls",
            payload_template={
                "attack_family": genai_fam.get("attack_id"),
                "capability_ids": caps,
                "channels": ["web", "agent"],
                "genai_features": {"prompt_injection_risk": 0.75, "agent_goal_anomaly": 0.7},
                "agent_mediated": True,
                "composite_source": genai_fam.get("attack_id"),
            },
            expected_outcome="PASS",
            rationale="Composite includes GenAI load-bearing family — inject context before payments",
        )
        rest = [s.model_copy(update={"step": i}) for i, s in enumerate(steps, start=2)]
        return [genai_step, *rest]

    def _enrich_with_kb_hints(self, plan: AttackPlan, family: dict) -> AttackPlan:
        hints = derive_payload_hints(family, self.kb.signals)
        if not hints:
            return plan

        updated_steps = []
        for step in plan.steps:
            tpl = dict(step.payload_template or {})
            if step.action_type == "register_customer":
                tpl.setdefault("trust_score", hints.get("trust_score", 0.65))
                if hints.get("pan"):
                    tpl.setdefault("pan", hints["pan"])
            elif step.action_type == "open_account" and hints.get("needs_account"):
                tpl.setdefault("balance", hints.get("balance", 75000))
            elif step.action_type == "onboard_merchant" and hints.get("needs_merchant"):
                tpl.setdefault("mcc", hints.get("mcc", "7995"))
                tpl.setdefault("declared_mcc", hints.get("declared_mcc", "5411"))
            elif step.action_type == "link_beneficiary" and hints.get("needs_beneficiary"):
                tpl.setdefault("risk_score", 0.25)
            elif step.action_type == "initiate_payment":
                if "amount" not in tpl and hints.get("amount"):
                    tpl["amount"] = hints["amount"]
                if hints.get("velocity_burst"):
                    tpl["velocity_burst"] = True
                if hints.get("structuring"):
                    tpl["structuring"] = True
            updated_steps.append(step.model_copy(update={"payload_template": tpl}))

        branch_label = plan.campaign_name.split("-", 1)[-1].strip() if "Tree-" in plan.campaign_name else None
        return plan.model_copy(update={"steps": updated_steps, "branch_label": branch_label})

    def _plan_is_too_generic(self, plan: AttackPlan, family: dict) -> bool:
        if not plan.steps:
            return True
        empty_templates = sum(1 for s in plan.steps if not s.payload_template)
        if empty_templates == len(plan.steps):
            return True
        pattern = classify_family(family)
        payment_steps = [s for s in plan.steps if s.action_type == "initiate_payment"]
        if pattern in ("velocity", "aml") and len(payment_steps) < 2:
            return True
        if pattern == "velocity":
            has_velocity_hint = any(
                s.payload_template.get("velocity_burst") or s.payload_template.get("velocity_index") is not None
                for s in payment_steps
            )
            if not has_velocity_hint and len(payment_steps) <= 1:
                return True
        if pattern == "aml":
            has_structuring = any(s.payload_template.get("structuring") for s in payment_steps)
            if not has_structuring and len(payment_steps) <= 1:
                return True
        return False

    def _finalize_llm_plan(
        self, llm_plan: AttackPlan, family: dict, hypothesis: Hypothesis
    ) -> AttackPlan:
        enriched = self._enrich_with_kb_hints(llm_plan, family)
        if not self._plan_is_too_generic(enriched, family):
            return enriched
        kb_plan = build_plan_from_family(
            family=family,
            stages=self.kb.stages,
            global_signals=self.kb.signals,
            hypothesis=hypothesis,
        )
        return kb_plan.model_copy(
            update={
                "campaign_name": enriched.campaign_name or kb_plan.campaign_name,
                "objective": enriched.objective or kb_plan.objective,
                "reasoning": (
                    f"{enriched.reasoning} "
                    f"[KB steps applied — pattern={classify_family(family)}]"
                ).strip(),
                "jailbreak_strategy": "kb+llm",
            }
        )

    def _plan_with_llm(self, hypothesis: Hypothesis, family: dict) -> Optional[AttackPlan]:
        llm = get_llm()
        if llm is None:
            return None
        try:
            from langchain.output_parsers import PydanticOutputParser
            from backend.llm import invoke_text

            parser = PydanticOutputParser(pydantic_object=AttackPlan)
            stage_controls = self.kb.get_stage_controls(family.get("lifecycle_stage") or "")
            family_signals = self.kb.get_signals_for_family(family.get("attack_id"))
            pattern = classify_family(family)
            hints = derive_payload_hints(family, self.kb.signals)
            attack_flow = family.get("attack_flow") or []
            composites = hypothesis.composite_families or []

            composite_note = ""
            if composites:
                composite_note = (
                    f"\nThis is part of a composite with partners {composites}. "
                    "Include simulate_genai_context if GenAI is involved, and "
                    "onboard_merchant / link_beneficiary when partners require them.\n"
                )

            prompt = f"""Build an AttackPlan for red-team sandbox simulation.

PRIMARY RULE: Derive every step from the KB attack_flow — NOT a generic onboarding funnel.
Pattern classification: {pattern}
Family ID: {family.get('attack_id')}
Lifecycle stage: {family.get('lifecycle_stage')}
{composite_note}
Hypothesis:
{hypothesis.model_dump_json(indent=2)}

KB attack_flow (use as step sequence):
{json.dumps(attack_flow, indent=2)}

KB payload hints (MUST populate payload_template on each step):
{json.dumps(hints, indent=2)}

Stage controls to target: {stage_controls}
Family detection signals: {json.dumps(family_signals[:5], indent=2)}

Allowed sandbox action_types:
  register_customer, register_device, open_account, onboard_merchant,
  link_beneficiary, initiate_payment, simulate_genai_context, authenticate

Requirements:
1. primary_family MUST be "{hypothesis.primary_family}"
2. Each step MUST have a non-empty payload_template with concrete values
3. For velocity/splitting families: multiple initiate_payment steps
4. For AML/structuring families: multiple initiate_payment steps below threshold
5. Include simulate_genai_context when family is GenAI load-bearing
6. Skip merchant/onboard steps unless pattern is merchant or composites need them

{parser.get_format_instructions()}"""

            system = (
                "You are a payment fraud red-team planner. Return only valid JSON for AttackPlan. "
                "Never return empty payload_template objects."
            )
            text = invoke_text(llm, system, prompt)
            if not text:
                return None
            plan = parser.parse(text)
            if plan.primary_family != hypothesis.primary_family:
                plan = plan.model_copy(update={"primary_family": hypothesis.primary_family})
            return plan
        except Exception as exc:
            print(f"[AttackPlanner] LLM fallback to KB builder: {exc}")
            return None
