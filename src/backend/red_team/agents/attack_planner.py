"""
Attack Planner Agent
INPUT: Hypothesis + KB API (family details)
OUTPUT: AttackPlan with steps, target controls, payload templates
"""

import json
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langchain.output_parsers import PydanticOutputParser

from ..schemas import Hypothesis, AttackPlan, PlanStep
from ..utils import KnowledgeBaseClient


class AttackPlanner:
    """
    Attack Planner Agent.
    Converts a Hypothesis into a detailed, step-by-step AttackPlan.
    """
    
    def __init__(self, model_name: str = "gemini-3.6-flash"):
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.7)
        self.kb = KnowledgeBaseClient()
        self.parser = PydanticOutputParser(pydantic_object=AttackPlan)
        
        self.prompt_template = PromptTemplate(
            input_variables=["hypothesis", "family_details", "available_stages", "format_instructions"],
            template="""
You are an Attack Planner for a payment fraud red team. Convert a hypothesis into a detailed, step-by-step attack campaign.

## Hypothesis:
{hypothesis}

## Attack Family Details (from Knowledge Base):
{family_details}

## Available Lifecycle Stages:
{available_stages}

## Chain-of-Thought Instructions:
1. First, understand the attack family's prerequisites and attack flow.
2. Second, identify which lifecycle stages need to be traversed.
3. Third, sequence the steps from entry point to final objective.
4. Fourth, determine which controls each step targets.
5. Fifth, design realistic payload templates for each step.

## Example (Velocity Evasion Plan):
Campaign Name: "Low-and-Slow Velocity Bypass"
Objective: Execute ₹50,000 payment without triggering controls
Target Stages: ["Payment_Initiation", "Authorization"]
Primary Family: AML-001
Selected Variant: Pattern-Free Movement
Steps:
  - Step 1: Initialize device, Target: Device, Payload: {{"device_id": "D001", "is_new": true}}, Outcome: PASS
  - Step 2: Small purchase ₹1,000, Target: Risk, Payload: {{"amount": 1000}}, Outcome: PASS
  - Step 3: Medium purchase ₹5,000, Target: Risk, Payload: {{"amount": 5000}}, Outcome: PASS
  - Step 4: High purchase ₹50,000, Target: Authorization, Payload: {{"amount": 50000}}, Outcome: BLOCK

## Return Format (JSON only, matching schema):
{format_instructions}

## Rules:
- Return ONLY valid JSON matching the schema.
- Each step must have a clear target_control.
- Payload templates should be generic placeholders that the Generator will fill.
- Provide clear reasoning for the sequence.
"""
        )
    
    def plan(self, hypothesis: Hypothesis) -> AttackPlan:
        """
        Plan an attack campaign from a hypothesis.
        INPUT: Hypothesis
        OUTPUT: AttackPlan
        """
        # 1. Format hypothesis
        hypothesis_dict = hypothesis.model_dump()
        hypothesis_str = json.dumps(hypothesis_dict, indent=2)
        
        # 2. Fetch family details from KB
        family_id = hypothesis.primary_family
        family_details = "No details available"
        if family_id and family_id != "COMPOSITE":
            detail = self.kb.get_family(family_id)
            if detail:
                family_details = json.dumps(detail, indent=2)
        
        # 3. Available stages
        stages = [
            "Identity_KYC", "Account_Creation", "Device_Session", "Authentication",
            "Payment_Initiation", "Merchant", "Acquirer", "Gateway_Processor",
            "Payment_Rail", "Authorization", "Settlement", "Cash_Out_Mule",
            "AML_Compliance", "Third_Party_Open_Banking", "AI_Agent_Commerce"
        ]
        
        # 4. Format instructions
        format_instructions = self.parser.get_format_instructions()
        
        # 5. Build prompt
        prompt = self.prompt_template.format(
            hypothesis=hypothesis_str,
            family_details=family_details,
            available_stages=", ".join(stages),
            format_instructions=format_instructions
        )
        
        # 6. Invoke LLM
        messages = [
            SystemMessage(content="You are an Attack Planner. Return ONLY valid JSON matching the schema."),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            plan = self.parser.parse(response.content)
            return plan
        except Exception as e:
            print(f"⚠️ Attack Planner failed: {e}")
            return self._get_fallback_plan(hypothesis)
    
    def _get_fallback_plan(self, hypothesis: Hypothesis) -> AttackPlan:
        """Fallback plan."""
        return AttackPlan(
            campaign_name=f"Attack: {hypothesis.name}",
            objective="Bypass payment controls",
            target_stages=["Payment_Initiation", "Authorization"],
            primary_family=hypothesis.primary_family,
            selected_variant=hypothesis.suggested_variant or "Generic",
            steps=[
                PlanStep(
                    step=1,
                    action="Initialize device",
                    target_control="Device",
                    payload_template={"device_id": "D001", "is_new": True},
                    expected_outcome="PASS",
                    rationale="Establish device presence"
                ),
                PlanStep(
                    step=2,
                    action="Low-value transaction",
                    target_control="Risk",
                    payload_template={"amount": 1000},
                    expected_outcome="PASS",
                    rationale="Build trust with low amount"
                ),
                PlanStep(
                    step=3,
                    action="Medium-value transaction",
                    target_control="Risk",
                    payload_template={"amount": 5000},
                    expected_outcome="PASS",
                    rationale="Gradual escalation"
                ),
                PlanStep(
                    step=4,
                    action="High-value transaction",
                    target_control="Authorization",
                    payload_template={"amount": 50000},
                    expected_outcome="BLOCK",
                    rationale="Final target"
                )
            ],
            success_criteria="High-value transaction is approved",
            estimated_complexity="medium",
            reasoning="Escalate transaction amounts gradually to bypass velocity and amount controls"
        )