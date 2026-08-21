"""
Failure Analyzer Agent
INPUT: Sandbox Response + Plan + Payload
OUTPUT: AnalysisResult (outcome, blocking_control, learnings, mutations)
"""

import json
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langchain.output_parsers import PydanticOutputParser

from ..schemas import AnalysisResult, AttackPlan, Payload
from ..utils import KnowledgeBaseClient


class FailureAnalyzer:
    """
    Failure Analyzer Agent.
    Parses Sandbox responses to learn why attacks succeed or fail.
    """
    
    def __init__(self, model_name: str = "gemini-3.6-flash"):
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.3)
        self.kb = KnowledgeBaseClient()
        self.parser = PydanticOutputParser(pydantic_object=AnalysisResult)
        
        self.prompt_template = PromptTemplate(
            input_variables=["sandbox_response", "attack_payload", "plan", "family_details", "format_instructions"],
            template="""
You are a Failure Analyzer for a payment fraud red team. Analyze the Sandbox response to understand why the attack succeeded or failed.

## Attack Payload:
{attack_payload}

## Attack Plan:
{plan}

## Attack Family Details (from KB):
{family_details}

## Sandbox Response:
{sandbox_response}

## Chain-of-Thought Instructions:
1. Determine the outcome: success or failure.
2. If failure, identify which control blocked the attack (KYC, Device, Auth, Risk, Authorization, Settlement).
3. Identify the specific rule or ML threshold that caused the decision.
4. Extract key learnings for future attacks.
5. Suggest specific mutations to bypass this control.

## Return Format (JSON only, matching schema):
{format_instructions}

## Rules:
- Return ONLY valid JSON matching the schema.
- The `blocking_control` must be one of: KYC, Device, Auth, Risk, Authorization, Settlement.
- `outcome` must be "success" or "failure".
- Provide specific, actionable learnings and mutations.
"""
        )
    
    def analyze(self, sandbox_response: Dict[str, Any], payload: Payload, plan: AttackPlan) -> AnalysisResult:
        """
        Analyze the Sandbox response.
        INPUT: Sandbox Response, Payload, Plan
        OUTPUT: AnalysisResult
        """
        # 1. Extract key info
        decision = sandbox_response.get("decision", "UNKNOWN")
        reason = sandbox_response.get("reason", "unknown")
        journey = sandbox_response.get("journey", [])
        risk_score = sandbox_response.get("state", {}).get("risk_score", 0)
        
        outcome = "success" if decision == "ALLOW" else "failure"
        
        # 2. Find blocking control
        blocking_control = None
        blocking_reason = reason
        
        for step in journey:
            if step.get("step") == "Authorization":
                result = step.get("result", {})
                if result.get("decision") == "BLOCK":
                    blocking_control = "Authorization"
                break
            elif step.get("step") == "Risk":
                result = step.get("result", {})
                if result.get("risk_score", 0) > 0.6:
                    blocking_control = "Risk"
                    blocking_reason = f"Risk score {result.get('risk_score', 0)}"
                break
            elif step.get("step") == "KYC":
                if step.get("result", {}).get("status") == "FAIL":
                    blocking_control = "KYC"
                break
            elif step.get("step") == "Device":
                if step.get("result", {}).get("status") == "FLAG":
                    blocking_control = "Device"
                break
            elif step.get("step") == "Authentication":
                if step.get("result", {}).get("status") == "FAIL":
                    blocking_control = "Authentication"
                break
            elif step.get("step") == "Settlement":
                if step.get("result", {}).get("status") == "FAIL":
                    blocking_control = "Settlement"
                break
        
        # 3. Generate learnings and mutations using LLM
        family_detail = self.kb.get_family(plan.primary_family) if plan.primary_family != "COMPOSITE" else None
        
        format_instructions = self.parser.get_format_instructions()
        
        prompt = self.prompt_template.format(
            sandbox_response=json.dumps(sandbox_response, indent=2),
            attack_payload=payload.model_dump_json(indent=2),
            plan=plan.model_dump_json(indent=2),
            family_details=json.dumps(family_detail, indent=2) if family_detail else "No details available",
            format_instructions=format_instructions
        )
        
        messages = [
            SystemMessage(content="You are a Failure Analyzer. Return ONLY valid JSON matching the schema."),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            result = self.parser.parse(response.content)
            return result
        except Exception as e:
            print(f"⚠️ Failure Analyzer LLM failed: {e}")
            return self._get_fallback_analysis(outcome, blocking_control, blocking_reason, risk_score, journey)
    
    def _get_fallback_analysis(self, outcome: str, blocking_control: str, blocking_reason: str, risk_score: float, journey: list) -> AnalysisResult:
        """Fallback analysis."""
        if outcome == "success":
            learnings = ["Attack bypassed all controls", f"Risk score was {risk_score}"]
            mutations = ["Test with higher amount", "Test with different merchant"]
        else:
            learnings = [f"Blocked by {blocking_control}: {blocking_reason}"]
            mutations = [f"Reduce amount to lower risk score", "Use older device to reduce device risk"]
        
        return AnalysisResult(
            outcome=outcome,
            blocking_control=blocking_control,
            blocking_reason=blocking_reason,
            risk_score=risk_score,
            learnings=learnings,
            mutation_suggestions=mutations,
            confidence=0.8,
            journey_trace=journey
        )