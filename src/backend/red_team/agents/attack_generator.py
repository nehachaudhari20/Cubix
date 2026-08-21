"""
Attack Generator Agent
INPUT: AttackPlan + KB API + Baseline CSV + LLM
OUTPUT: Sequence of Payloads
"""

import uuid
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage

from ..schemas import AttackPlan, Payload, GeneratedSequence
from ..utils import KnowledgeBaseClient, BaselineLoader


class AttackGenerator:
    """
    Attack Generator Agent.
    Hybrid: KB for structure, LLM for narrative, Baseline for statistics.
    """
    
    def __init__(self, model_name: str = "gemini-3.6-flash"):
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.8)
        self.kb = KnowledgeBaseClient()
        self.baseline = BaselineLoader()
        
        self.narrative_prompt = PromptTemplate(
            input_variables=["family", "variant", "step", "total_steps", "amount", "target_control"],
            template="""
Generate a realistic, short transaction narrative for a payment fraud attack.

Attack Family: {family}
Variant: {variant}
Step: {step}/{total_steps}
Amount: ₹{amount}
Target Control: {target_control}

Return a 1-2 sentence narrative that would appear in a payment system log.
Example: "Payment to vendor for procurement of IT services" or "Subscription renewal for software license".
Be realistic and varied.
"""
        )
    
    def generate_sequence(self, plan: AttackPlan) -> GeneratedSequence:
        """
        Generate a complete sequence of payloads from a plan.
        INPUT: AttackPlan
        OUTPUT: GeneratedSequence
        """
        family_id = plan.primary_family
        variant = plan.selected_variant
        
        # Fetch family details from KB for context
        family_detail = self.kb.get_family(family_id) if family_id != "COMPOSITE" else None
        
        payloads = []
        base_customer_id = f"C_{uuid.uuid4().hex[:8]}"
        base_device_id = f"D_{uuid.uuid4().hex[:8]}"
        
        num_steps = len(plan.steps)
        
        for idx, step in enumerate(plan.steps):
            # 1. Sample amount from baseline
            base_amount = self.baseline.sample_amount()
            # Apply escalation based on step
            escalation_factor = 1 + (idx / num_steps) * 5
            amount = base_amount * escalation_factor
            
            # If plan has specific amount, override
            if "amount" in step.payload_template:
                amount = step.payload_template.get("amount", amount)
            
            # 2. Sample rail from baseline
            rail = self.baseline.sample_rail()
            
            # 3. Sample merchant risk from baseline
            merchant_risk = self.baseline.sample_merchant_risk()
            if idx > num_steps // 2:
                merchant_risk = min(1.0, merchant_risk + 0.3)
            
            # 4. Device: first step = new, subsequent = known
            is_new_device = idx == 0
            
            # 5. Beneficiary: final step = new beneficiary
            is_new_beneficiary = idx == num_steps - 1
            
            # 6. Generate narrative using LLM
            narrative = self._generate_narrative(
                family=family_id,
                variant=variant,
                step=idx+1,
                total_steps=num_steps,
                amount=amount,
                target_control=step.target_control
            )
            
            # 7. Build payload
            payload = Payload(
                transaction_id=f"txn_attack_{uuid.uuid4().hex[:8]}",
                timestamp=(datetime.now() + timedelta(hours=idx * 3 + random.randint(0, 60))).isoformat(),
                customer_id=base_customer_id,
                device_id=base_device_id,
                amount=round(amount, 2),
                currency="INR",
                payment_rail=rail,
                transaction_type=self.baseline.sample_transaction_type(),
                authentication_method="otp",
                merchant_id=f"MCH_{uuid.uuid4().hex[:8]}",
                merchant_risk_score=round(merchant_risk, 3),
                is_new_device=is_new_device,
                is_new_beneficiary=is_new_beneficiary,
                beneficiary_account_id=f"BEN_{uuid.uuid4().hex[:8]}" if is_new_beneficiary else None,
                narrative=narrative,
                step=idx+1,
                total_steps=num_steps,
                is_final=idx == num_steps - 1,
                campaign_id=plan.campaign_name.replace(" ", "_").lower(),
                attack_family=family_id,
                attack_variant=variant,
                target_control=step.target_control,
                expected_outcome=step.expected_outcome
            )
            payloads.append(payload)
        
        return GeneratedSequence(
            campaign_id=plan.campaign_name.replace(" ", "_").lower(),
            payloads=payloads,
            total_payloads=len(payloads)
        )
    
    def _generate_narrative(self, family: str, variant: str, step: int, total_steps: int, amount: float, target_control: str) -> str:
        """Generate narrative using LLM."""
        prompt = self.narrative_prompt.format(
            family=family,
            variant=variant,
            step=step,
            total_steps=total_steps,
            amount=round(amount, 2),
            target_control=target_control
        )
        
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception:
            return f"Step {step} of {total_steps}: {family} attack targeting {target_control}"