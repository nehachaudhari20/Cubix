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


# Benign-but-unusual activity per surface. These are the legitimate cases most
# likely to be confused with an attack: a real video KYC, a genuine multi-scope
# consent, an agent making an authorised purchase, a customer on a new phone.
SURFACE_LEGITIMATE_PROFILES: Dict[str, Dict[str, Any]] = {
    "agent": {
        "agent_verified": True,
        "mandate_scope": ["read", "purchase"],
        "tool_scope": ["search", "checkout", "payment_api"],
        "requested_tools": ["search", "checkout"],
        "spend_limit": 50000.0,
        "requested_amount": 12000.0,
        "agent_mediated": True,
        "genai_features": {"agentic_planning_score": 0.25, "personalization_score": 0.30},
        "_reason": "Authorised agent purchase inside its mandate and tool scope",
    },
    "auth_se": {
        "channel": "web",
        "authentication_method": "biometric",
        "victim_coerced": False,
        "genai_features": {"social_engineering_score": 0.10},
        "_reason": "Ordinary customer authentication on a known channel",
    },
    "kyc": {
        "evidence_type": "video_kyc",
        "genai_features": {"identity_consistency_score": 0.95, "deepfake_identity_score": 0.08},
        "_reason": "Genuine video KYC — real liveness, consistent identity",
    },
    "open_banking": {
        "scopes": ["accounts.read", "accounts.write"],
        "tpp_licensed": True,
        "tpp_registration_age_days": 900,
        "tpp_risk_score": 0.10,
        "genai_features": {"personalization_score": 0.20},
        "_reason": "Licensed TPP granted a normal multi-scope consent",
    },
    "device": {
        "remote_access_active": False,
        "accessibility_service_active": False,
        "screen_overlay_active": False,
        "headless_client": False,
        "mean_interaction_interval_ms": 420.0,
        "behavioural_variance": 0.48,
        "genai_features": {"scale_automation_score": 0.05},
        "_reason": "Human-paced session with normal interaction jitter",
    },
    "network": {
        "member_customer_ids": [],
        "aml_narrative_submitted": False,
        "genai_features": {"network_orchestration_score": 0.05},
        "_reason": "Single-account activity with no ring structure",
    },
}


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

    def generate(self, count: int = 3, include_surfaces: bool = True) -> List[EvidenceRecord]:
        records: List[EvidenceRecord] = []
        for _ in range(max(1, count)):
            record = self.generate_one()
            if record:
                records.append(record)
        if include_surfaces:
            records.extend(self.generate_surface_negatives(count_per_surface=count))
        return records

    def generate_surface_negatives(self, count_per_surface: int = 3) -> List[EvidenceRecord]:
        """
        Legitimate-but-unusual activity on each non-payment surface.

        Without these the model has *no* negative examples on the agent, auth_se,
        kyc, consent, device and network surfaces — every row it ever sees there is
        an attack, so it learns "this surface means fraud" and flags genuine video
        KYC, real broad consents and legitimate agent payments. That is a false
        positive on a real customer, which is the cost the challenge explicitly
        asks us to keep low.

        Inverted-guardrail logic, same as the payment case: run benign parameters
        and only keep the row as a negative if the sandbox actually allows it.
        """
        records: List[EvidenceRecord] = []
        for surface, profile in SURFACE_LEGITIMATE_PROFILES.items():
            for index in range(max(1, count_per_surface)):
                record = self._surface_negative_one(surface, profile, index)
                if record:
                    records.append(record)
        return records

    def _surface_negative_one(
        self,
        surface: str,
        profile: Dict[str, Any],
        index: int,
    ) -> Optional[EvidenceRecord]:
        from backend.taxonomy import SURFACE_ENTRY_ACTION

        customer_id = f"HN_{surface[:6]}_{uuid.uuid4().hex[:6]}"
        device_id = f"HND_{uuid.uuid4().hex[:6]}"

        self.sandbox.execute("register_customer", {
            "customer_id": customer_id,
            "name": "Legitimate Surface Customer",
            "pan": "HN0000002",
            "dob": "1985-03-22",
            "address": "Verified Address",
            "trust_score": 0.80,
            "verified": True,
            "account_age_days": 600,
        })
        self.sandbox.execute("register_device", {
            "device_id": device_id,
            "customer_id": customer_id,
            "fingerprint": {"browser": "Chrome", "os": "Android"},
        })

        payload = {
            "customer_id": customer_id,
            "device_id": device_id,
            **profile,
        }
        action = SURFACE_ENTRY_ACTION[surface]
        observation = self.sandbox.execute(action, payload)

        # Only a genuinely allowed event is a usable negative. If the sandbox
        # challenges or blocks it, the "legitimate" profile was not legitimate.
        if observation.decision != "ALLOW":
            return None

        from .features import FeatureBuilder

        features = FeatureBuilder().build_control_surface(
            action, payload, self.sandbox.get_state(), observation.state_snapshot
        )
        features["meta_hard_negative"] = True

        record = EvidenceRecord(
            evidence_id=f"hn_{uuid.uuid4().hex[:10]}",
            campaign_id=f"hard_negative_{surface}_{index}_{uuid.uuid4().hex[:4]}",
            attack_family="HARD-NEGATIVE",
            action_type=action,
            surface=surface,
            scenario_type="legitimate_surface_activity",
            sandbox_decision=str(observation.decision),
            evasion_outcome="passed_guardrails",
            analysis_outcome="legitimate_suspicious",
            attack_variant="inverted_guardrail_surface",
            control_triggers=list(observation.control_triggers or []),
            ml_score=observation.ml_score,
            rule_risk=observation.rule_risk,
            risk_score=observation.risk_score,
            label=0,
            features=features,
            step=1,
            source="hard_negative_generator",
            timestamp=datetime.now(timezone.utc).isoformat(),
            is_hard_negative=True,
            legitimacy_reason=profile.get("_reason", "Benign surface activity allowed by controls"),
        )
        self.buffer.append(record)
        return record

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
