"""
Hard Negative Generator — inverted DeepTeam guardrails for Blue Team training.

Generate suspicious-but-legitimate transactions. If sandbox controls do NOT
block them, label as hard negatives (label=0) for FraudShield training.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.sandbox import PaymentSandbox
from backend.sandbox.rules.compiled_controls import CompiledControlSet, get_global_compiled_controls
from backend.sandbox.rules.control_compiler import ControlCompiler

from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH
from .schemas import EvidenceRecord


class HardNegativeGenerator:
    """Produce hard-negative evidence rows via inverted guardrail logic."""

    def __init__(
        self,
        sandbox: Optional[PaymentSandbox] = None,
        buffer: Optional[EvidenceBuffer] = None,
        compiled_controls: Optional[CompiledControlSet] = None,
    ):
        self.compiled = compiled_controls or get_global_compiled_controls() or ControlCompiler().compile()
        self.sandbox = sandbox or PaymentSandbox(compiled_controls=self.compiled)
        buffer_path = os.environ.get("HARD_NEGATIVE_BUFFER_PATH", DEFAULT_BUFFER_PATH)
        self.buffer = buffer or EvidenceBuffer(buffer_path)

    def generate(self, count: int = 3) -> List[EvidenceRecord]:
        records: List[EvidenceRecord] = []
        for _ in range(max(1, count)):
            record = self.generate_one()
            if record:
                records.append(record)
        return records

    def generate_one(self) -> Optional[EvidenceRecord]:
        customer_id = f"HN_C_{uuid.uuid4().hex[:6]}"
        device_id = f"HN_D_{uuid.uuid4().hex[:6]}"
        txn_id = f"hn_{uuid.uuid4().hex[:8]}"

        self.sandbox.execute("register_customer", {
            "customer_id": customer_id,
            "name": "Legitimate Hard Negative Customer",
            "pan": "HN0000001",
            "dob": "1988-06-15",
            "address": "Verified Address",
            "trust_score": 0.82,
            "verified": True,
        })
        self.sandbox.execute("register_device", {
            "device_id": device_id,
            "customer_id": customer_id,
            "fingerprint": {"browser": "Chrome", "os": "Android", "new_device": True},
        })

        amount_limit = self.compiled.get_stage_defaults("Payment Initiation").get("amount_limit_tier1", 25000)
        suspicious_amount = round(float(amount_limit) * 0.92, 2)

        payment = {
            "transaction_id": txn_id,
            "customer_id": customer_id,
            "device_id": device_id,
            "amount": suspicious_amount,
            "payment_rail": "UPI",
            "authentication_method": "otp",
            "merchant_risk_score": 0.25,
            "hour": 2,
            "is_new_device": True,
        }
        observation = self.sandbox.execute("initiate_payment", payment)
        decision = observation.decision
        triggers = observation.control_triggers or []
        risk_score = observation.risk_score
        rule_risk = observation.rule_risk
        ml_score = observation.ml_score

        if decision in ("BLOCK", "CHALLENGE"):
            return None

        if len(triggers) >= 3:
            return None

        record = EvidenceRecord(
            evidence_id=f"hn_{uuid.uuid4().hex[:10]}",
            campaign_id=f"hard_negative_{uuid.uuid4().hex[:6]}",
            attack_family="HARD-NEGATIVE",
            action_type="initiate_payment",
            sandbox_decision=str(decision),
            evasion_outcome="passed_guardrails",
            analysis_outcome="legitimate_suspicious",
            blocking_control=None,
            attack_variant="inverted_guardrail",
            control_triggers=list(triggers),
            ml_score=ml_score,
            rule_risk=rule_risk,
            risk_score=risk_score,
            label=0,
            features={
                "amount": suspicious_amount,
                "hour_of_day": 2,
                "is_new_device": True,
                "is_night": True,
                "trust_score": 0.82,
                "meta_hard_negative": True,
            },
            amount=suspicious_amount,
            step=1,
            source="hard_negative_generator",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_hard_negative=True,
            legitimacy_reason="Suspicious profile passed sandbox controls without block",
        )
        self.buffer.append(record)
        return record
