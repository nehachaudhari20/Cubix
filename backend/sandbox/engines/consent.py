"""
Consent / Open Banking Engine — STG-0042 / STG-0043.

Adjudicates the `open_banking` surface: over-broad consent, deceptive consent
UX, scope creep after grant, stolen-token replay, and fake TPP registration.

Granted consent persists, so scope creep and token replay are only meaningful
because the original grant is still in state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..state import SandboxState, SyntheticConsent, SyntheticTPP


# Scopes that materially increase exposure if granted
SENSITIVE_SCOPES = frozenset(
    {"payments.initiate", "accounts.write", "standing_orders.write", "data.export_all"}
)

# A "normal" retail consent grants at most this many scopes
TYPICAL_SCOPE_COUNT = 3


class ConsentEngine:
    """Consent scope, TPP legitimacy, and token-lifecycle checks."""

    def __init__(self, state: SandboxState):
        self.state = state

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        customer_id = payload.get("customer_id") or ""
        genai = payload.get("genai_features") or {}
        scopes = [str(s) for s in (payload.get("scopes") or ["accounts.read"])]

        tpp = self._resolve_tpp(payload)

        # --- TPP legitimacy ------------------------------------------------------
        if not tpp.is_licensed:
            flags.append("ob_unlicensed_tpp")
        if tpp.registration_age_days < 30:
            flags.append("ob_newly_registered_tpp")
        if tpp.risk_score >= 0.60:
            flags.append("ob_high_risk_tpp")
        if float(genai.get("synthetic_content_score") or 0) >= 0.60 and payload.get("tpp_registration"):
            flags.append("ob_synthetic_tpp_application")

        # --- consent scope -------------------------------------------------------
        sensitive = sorted(set(scopes) & SENSITIVE_SCOPES)
        if len(scopes) > TYPICAL_SCOPE_COUNT:
            flags.append("ob_excessive_consent_scope")
        if sensitive:
            flags.append("ob_sensitive_scope_requested")
        breadth = min(1.0, len(scopes) / 8.0 + 0.2 * len(sensitive))
        if float(genai.get("personalization_score") or 0) >= 0.65:
            flags.append("ob_deceptive_consent_presentation")

        # --- existing consent lifecycle ------------------------------------------
        consent_id = payload.get("consent_id")
        existing = self.state.get_consent(consent_id) if consent_id else None
        replay = False
        escalation = False

        if existing is not None:
            if existing.is_expired or not existing.is_active:
                flags.append("ob_inactive_consent_reused")
                replay = True
            token_ref = payload.get("token_ref")
            if token_ref and existing.token_ref and token_ref != existing.token_ref:
                flags.append("ob_consent_token_mismatch")
                replay = True
            new_scopes = sorted(set(scopes) - set(existing.scopes))
            if new_scopes:
                flags.append("ob_consent_scope_creep")
                escalation = True
                existing.scope_escalations += 1
                existing.scopes = sorted(set(existing.scopes) | set(scopes))
            existing.use_count += 1
            if existing.use_count > 20:
                flags.append("ob_consent_usage_anomaly")
            consent = existing
        else:
            consent = SyntheticConsent(
                consent_id=consent_id or f"cns_{uuid.uuid4().hex[:8]}",
                customer_id=customer_id,
                tpp_id=tpp.tpp_id,
                scopes=scopes,
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(days=int(payload.get("consent_days", 90))),
                token_ref=payload.get("token_ref") or f"tok_{uuid.uuid4().hex[:8]}",
                use_count=1,
            )
            self.state.consents[consent.consent_id] = consent

        if payload.get("stolen_token"):
            flags.append("ob_stolen_token_presented")
            replay = True

        risk = min(1.0, 0.15 * len(flags) + breadth * 0.25)
        status = "FAIL" if "ob_unlicensed_tpp" in flags and sensitive else "PASS"

        return {
            "status": status,
            "stage": "STG-0042",
            "engine": "consent",
            "flags": flags,
            "consent_risk": round(risk, 4),
            "consent_id": consent.consent_id,
            "tpp_id": tpp.tpp_id,
            "scopes": consent.scopes,
            "consent_scope_breadth": round(breadth, 4),
            "sensitive_scopes": sensitive,
            "token_replay": replay,
            "scope_escalation": escalation,
            "scope_escalations_total": consent.scope_escalations,
        }

    def _resolve_tpp(self, payload: Dict[str, Any]) -> SyntheticTPP:
        tpp_id = payload.get("tpp_id") or f"tpp_{uuid.uuid4().hex[:6]}"
        tpp = self.state.get_tpp(tpp_id)
        if tpp is None:
            tpp = SyntheticTPP(
                tpp_id=tpp_id,
                name=payload.get("tpp_name") or "Third Party Provider",
                created_at=datetime.now(),
                is_licensed=bool(payload.get("tpp_licensed", True)),
                registration_age_days=int(payload.get("tpp_registration_age_days", 365)),
                risk_score=float(payload.get("tpp_risk_score", 0.2)),
            )
            self.state.tpps[tpp_id] = tpp
        return tpp
