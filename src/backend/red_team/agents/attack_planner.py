"""
Attack Planner Agent — KB + DeepTeam jailbreak strategies (Crescendo / Tree / Sequential).
"""

from __future__ import annotations

import json
from typing import List, Optional

from ..schemas import Hypothesis, AttackPlan
from ..agent_helpers import OfflineKnowledge, get_llm, use_llm
from ..kb_campaign_builder import build_plan_from_family, derive_payload_hints
from ..deepteam.jailbreak_planner import JailbreakPlanner
from ..deepteam.strategy_config import resolve_jailbreak_strategy
from ..deepteam.schemas import JailbreakStrategy


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

        strategy = resolve_jailbreak_strategy(hypothesis)

        if strategy is None:
            if get_llm() and use_llm():
                llm_plan = self._plan_with_llm(hypothesis, family)
                if llm_plan:
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

    def _enrich_with_kb_hints(self, plan: AttackPlan, family: dict) -> AttackPlan:
        hints = derive_payload_hints(family, self.kb.signals)
        if not hints:
            return plan
        updated_steps = []
        for step in plan.steps:
            tpl = dict(step.payload_template or {})
            if step.action_type == "initiate_payment":
                if "amount" not in tpl and hints.get("amount"):
                    tpl["amount"] = hints["amount"]
                if hints.get("velocity_burst"):
                    tpl["velocity_burst"] = True
            if step.action_type == "register_customer" and "trust_score" not in tpl:
                tpl.setdefault("trust_score", hints.get("trust_score", 0.65))
            updated_steps.append(step.model_copy(update={"payload_template": tpl}))
        branch_label = plan.campaign_name.split("-", 1)[-1].strip() if "Tree-" in plan.campaign_name else None
        return plan.model_copy(update={"steps": updated_steps, "branch_label": branch_label})

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

            prompt = f"""Convert this KB family into an AttackPlan with sandbox action_types:
register_customer, register_device, open_account, onboard_merchant, link_beneficiary, initiate_payment

Hypothesis: {hypothesis.model_dump_json(indent=2)}

Family: {json.dumps(family, indent=2)[:4000]}

Stage controls: {stage_controls}
Family signals: {json.dumps(family_signals[:5], indent=2)}

Attack flow from KB: {family.get('attack_flow')}

{parser.get_format_instructions()}"""

            text = invoke_text(llm, "Return only valid JSON for AttackPlan.", prompt)
            if not text:
                return None
            return parser.parse(text)
        except Exception as exc:
            print(f"[AttackPlanner] LLM fallback to KB builder: {exc}")
            return None
