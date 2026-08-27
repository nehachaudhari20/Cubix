"""
KYC Evidence Engine — STG-0019 / STG-0039 (Identity, Onboarding).

Adjudicates the `kyc` surface: deepfake biometrics, forged documents, liveness
bypass, synthetic-identity onboarding, and recovery-document fraud.

Accepting evidence mutates durable state — the customer becomes `verified` with a
raised trust score. That is the point: a deepfake that passes here makes every
later payment look legitimate, which is exactly the cross-surface consequence a
payment-only sandbox cannot represent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from ..state import SandboxState, SyntheticKYCSubmission


class KYCEvidenceEngine:
    """Document, biometric, and liveness adjudication for identity evidence."""

    def __init__(self, state: SandboxState):
        self.state = state

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        customer_id = payload.get("customer_id") or ""
        evidence_type = str(payload.get("evidence_type") or "document").lower()
        genai = payload.get("genai_features") or {}
        customer = self.state.get_customer(customer_id)

        deepfake = float(genai.get("deepfake_identity_score") or 0)
        biometric_spoof = float(genai.get("biometric_spoof_risk") or 0)
        liveness_bypass = float(genai.get("liveness_bypass_score") or 0)
        doc_forgery = float(genai.get("document_forgery_score") or 0)
        template_match = float(genai.get("document_template_match_score") or 0)
        synthetic_id = float(genai.get("synthetic_identity_score") or 0)
        kyc_deepfake = float(genai.get("kyc_deepfake_risk") or 0)

        # --- biometric / liveness ------------------------------------------------
        liveness_passed = True
        if evidence_type in ("biometric", "liveness", "video_kyc"):
            if max(deepfake, kyc_deepfake) >= 0.60:
                flags.append("kyc_deepfake_biometric_detected")
            if biometric_spoof >= 0.55:
                flags.append("kyc_biometric_spoof_indicators")
            if liveness_bypass >= 0.55:
                flags.append("kyc_liveness_bypass_attempt")
                liveness_passed = False

        # --- documents -----------------------------------------------------------
        document_verified = True
        if evidence_type in ("document", "recovery_document"):
            if doc_forgery >= 0.60:
                flags.append("kyc_document_forgery_detected")
                document_verified = False
            if template_match >= 0.65:
                flags.append("kyc_document_template_reuse")
        if evidence_type == "recovery_document":
            flags.append("kyc_recovery_evidence_submitted")

        # --- identity consistency ------------------------------------------------
        if synthetic_id >= 0.55:
            flags.append("kyc_synthetic_identity_indicators")
        consistency = float(genai.get("identity_consistency_score") or 1.0)
        if consistency < 0.60:
            flags.append("kyc_identity_inconsistent_across_evidence")

        # --- resubmission pattern (state-driven) ---------------------------------
        prior = self.state.get_kyc_submissions(customer_id)
        rejected_prior = [s for s in prior if not s.accepted]
        if len(rejected_prior) >= 2:
            flags.append("kyc_repeated_rejected_submissions")

        # Evidence is accepted unless a hard detection fired.
        hard_fail = any(
            f in flags
            for f in (
                "kyc_deepfake_biometric_detected",
                "kyc_document_forgery_detected",
                "kyc_liveness_bypass_attempt",
            )
        )
        accepted = not hard_fail

        submission = SyntheticKYCSubmission(
            submission_id=payload.get("submission_id") or f"kyc_{uuid.uuid4().hex[:8]}",
            customer_id=customer_id,
            evidence_type=evidence_type,
            created_at=datetime.now(),
            accepted=accepted,
            liveness_passed=liveness_passed,
            document_verified=document_verified,
            reason="accepted" if accepted else "evidence_rejected",
        )
        self.state.kyc_submissions[submission.submission_id] = submission

        # Cross-surface consequence: accepted evidence upgrades the identity.
        if accepted and customer is not None:
            customer.verified = True
            customer.trust_score = min(1.0, customer.trust_score + 0.20)

        risk = min(1.0, 0.17 * len(flags) + max(deepfake, doc_forgery, synthetic_id) * 0.25)
        return {
            "status": "PASS" if accepted else "FAIL",
            "stage": "STG-0019",
            "engine": "kyc_genai",
            "flags": flags,
            "kyc_risk": round(risk, 4),
            "evidence_type": evidence_type,
            "evidence_accepted": accepted,
            "liveness_passed": liveness_passed,
            "document_verified": document_verified,
            "submission_id": submission.submission_id,
            "prior_rejected_submissions": len(rejected_prior),
            "identity_upgraded": accepted and customer is not None,
        }
