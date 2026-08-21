"""
Threat Hunter Agent
INPUT: KB API + Memory Context
OUTPUT: List of Hypotheses
"""

import json
import requests
from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage, SystemMessage
from langchain.output_parsers import PydanticOutputParser

from ..schemas import Hypothesis, ThreatHunterOutput
from ..utils import KnowledgeBaseClient


class ThreatHunter:
    """
    Threat Hunter Agent.
    Discovers novel attack hypotheses using KB API and memory context.
    """
    
    def __init__(self, model_name: str = "gemini-3.6-flash"):
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.7)
        self.kb = KnowledgeBaseClient()
        self.parser = PydanticOutputParser(pydantic_object=ThreatHunterOutput)
        
        self.prompt_template = PromptTemplate(
            input_variables=["available_families", "family_details", "memory_context", "format_instructions"],
            template="""
You are a Threat Hunter for a payment fraud red team. Your goal is to discover NOVEL, UNTESTED attack hypotheses.

## Context:
- You are testing a synthetic payment system with controls at every stage (KYC, Device, Auth, Risk, Authorization, Settlement).
- The system has an ML-based fraud detector (FraudShield).
- You must find attacks that the system hasn't seen before.
- COMPOSITE attacks (combining multiple families) are highly valuable.

## Available Attack Families (from Knowledge Base):
{available_families}

## Detailed Family Information:
{family_details}

## Recent Memory (what has been tried and what worked/failed):
{memory_context}

## Chain-of-Thought Instructions:
1. Which families are UNTESTED or have LOW coverage?
2. Which COMPOSITE combinations could create novel behavior?
3. Are the prerequisites feasible in this environment?
4. What is the attack flow through the payment lifecycle?
5. Assign a novelty score (0-1) and success probability (0-1).

## Examples of Strong Hypotheses:
- "Trust Farming + Velocity Evasion": Build trust with low-value transactions, then execute high-value transfer.
- "Synthetic Identity + Merchant MCC Misrepresentation": Create fake merchant, misrepresent MCC, process high-risk transactions.
- "Prompt Injection + Agent Routing Manipulation": Inject hidden prompts into AI agent to route payments maliciously.

## Return Format (JSON only, matching schema):
{format_instructions}

## Rules:
- Return ONLY valid JSON that matches the schema.
- Do NOT include markdown, code blocks, or extra text.
- The `primary_family` must be a real family ID from the available list (or "COMPOSITE").
- For composite attacks, list all family IDs in `composite_families`.
- Provide clear chain-of-thought reasoning.
"""
        )
    
    def discover(self, memory_context: Optional[str] = None) -> ThreatHunterOutput:
        """
        Discover attack hypotheses.
        INPUT: Memory context (optional)
        OUTPUT: ThreatHunterOutput with list of hypotheses
        """
        # 1. Fetch families from KB
        families = self.kb.get_families()
        if not families:
            return self._get_fallback_output()
        
        # 2. Format for prompt
        available_ids = [f.get("attack_id", "") for f in families if f.get("attack_id")]
        available_str = "\n".join([f"  - {fid}" for fid in available_ids[:15]])
        
        # 3. Get details for key families
        family_details = []
        for fid in available_ids[:8]:
            detail = self.kb.get_family(fid)
            if detail:
                family_details.append(
                    f"  {fid}: {detail.get('name', fid)} — Stage: {detail.get('lifecycle_stage', 'Unknown')} — "
                    f"Variants: {detail.get('variants', [])[:3]}"
                )
        family_details_str = "\n".join(family_details) if family_details else "  (No details available)"
        
        # 4. Memory context
        memory = memory_context or """
Recent experiments:
- SIF-001 (Synthetic Identity): SUCCESS — bypassed KYC
- AUTH-001 (Phishing): PARTIAL — OTP captured but MFA blocked
- AML-001 (Evasion): FAILED — ML model detected pattern
- MCH-002 (Shell Merchant): SUCCESS — website passed verification
"""
        
        # 5. Format instructions
        format_instructions = self.parser.get_format_instructions()
        
        # 6. Build prompt
        prompt = self.prompt_template.format(
            available_families=available_str,
            family_details=family_details_str,
            memory_context=memory,
            format_instructions=format_instructions
        )
        
        # 7. Invoke LLM
        messages = [
            SystemMessage(content="You are a Threat Hunter. Return ONLY valid JSON matching the schema."),
            HumanMessage(content=prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            output = self.parser.parse(response.content)
            return output
        except Exception as e:
            print(f"⚠️ Threat Hunter LLM parsing failed: {e}")
            return self._get_fallback_output()
    
    def _get_fallback_output(self) -> ThreatHunterOutput:
        """Fallback hypotheses if KB or LLM fails."""
        return ThreatHunterOutput(
            hypotheses=[
                Hypothesis(
                    name="Velocity Evasion via Time Spreading",
                    primary_family="AML-001",
                    composite_families=[],
                    target_stages=["Authorization"],
                    novelty_score=0.6,
                    success_probability=0.65,
                    prerequisites=["Existing merchant account", "Control over transaction timing"],
                    attack_flow_summary="Spread transactions over 48 hours to bypass velocity limits",
                    reasoning="Velocity limits are time-window based; spreading may evade detection."
                ),
                Hypothesis(
                    name="Synthetic Merchant + MCC Misrepresentation",
                    primary_family="COMPOSITE",
                    composite_families=["MCH-001", "ACQ-004"],
                    target_stages=["Merchant", "Acquirer"],
                    novelty_score=0.85,
                    success_probability=0.55,
                    prerequisites=["GenAI for website generation", "Understanding of MCC risk tiers"],
                    attack_flow_summary="Create synthetic merchant with AI-generated front, misrepresent MCC",
                    reasoning="Combining merchant creation with MCC manipulation bypasses onboarding and monitoring."
                ),
                Hypothesis(
                    name="Agent Memory Poisoning for Unauthorized Transfers",
                    primary_family="AG-003",
                    composite_families=[],
                    target_stages=["AI_Agent_Commerce"],
                    novelty_score=0.9,
                    success_probability=0.4,
                    prerequisites=["Agent with stored payment credentials", "Access to external content"],
                    attack_flow_summary="Inject fabricated memories into agent to trigger unauthorized transfers",
                    reasoning="Memory poisoning exploits agent's trust in stored context."
                )
            ],
            confidence=0.8
        )