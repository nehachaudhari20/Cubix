"""
Attack Planner Agent — converts KB family hypotheses into executable sandbox plans.
Uses attack_flow, lifecycle stages, and detection signals from all three KB JSON files.
"""

import json
from typing import Optional

from ..schemas import Hypothesis, AttackPlan
from ..agent_helpers import OfflineKnowledge, get_llm, USE_LLM
from ..kb_campaign_builder import build_plan_from_family


class AttackPlanner:
    """Builds step-by-step campaigns mapped to sandbox action types from KB data."""

    def __init__(self, model_name: str = None):
        self.kb = OfflineKnowledge()
        self.llm = get_llm()

    def plan(self, hypothesis: Hypothesis) -> AttackPlan:
        family = self.kb.get_family(hypothesis.primary_family)
        if not family:
            raise ValueError(f"Family {hypothesis.primary_family} not found in KB")

        if self.llm and USE_LLM:
            result = self._plan_with_llm(hypothesis, family)
            if result:
                return result

        return build_plan_from_family(
            family=family,
            stages=self.kb.stages,
            global_signals=self.kb.signals,
            hypothesis=hypothesis,
        )

    def plan_from_family_id(self, family_id: str) -> AttackPlan:
        """Direct KB family → plan (used by continuous runner)."""
        family = self.kb.get_family(family_id)
        if not family:
            raise ValueError(f"Family {family_id} not found in KB")
        return build_plan_from_family(
            family=family,
            stages=self.kb.stages,
            global_signals=self.kb.signals,
        )

    def _plan_with_llm(self, hypothesis: Hypothesis, family: dict) -> Optional[AttackPlan]:
        try:
            from langchain.schema import HumanMessage, SystemMessage
            from langchain.output_parsers import PydanticOutputParser

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

            response = self.llm.invoke([
                SystemMessage(content="Return only valid JSON for AttackPlan."),
                HumanMessage(content=prompt),
            ])
            return parser.parse(response.content)
        except Exception as exc:
            print(f"[AttackPlanner] LLM fallback to KB builder: {exc}")
            return None
