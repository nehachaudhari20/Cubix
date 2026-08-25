"""Fraud investigator LLM judge (BadLikert-style). Phase 6 implementation stub."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from backend.llm import get_llm, invoke_text

from .schemas import FraudJudgeVerdict


class FraudInvestigatorJudge:
    """Evaluate sandbox outcomes and identify control gaps."""

    def evaluate(
        self,
        *,
        payload: Dict[str, Any],
        sandbox_response: Dict[str, Any],
        expected_control_ids: List[str],
        triggered_control_ids: Optional[List[str]] = None,
    ) -> FraudJudgeVerdict:
        triggered = triggered_control_ids or sandbox_response.get("control_triggers") or []
        missing = [cid for cid in expected_control_ids if cid not in triggered]
        outcome = sandbox_response.get("decision", "UNKNOWN")
        gap = outcome == "ALLOW" and bool(missing)

        summary = self._llm_summary(payload, sandbox_response, expected_control_ids, triggered, missing)
        if not summary:
            summary = (
                f"Decision {outcome}. Expected {expected_control_ids}, triggered {triggered}. "
                f"Missing: {missing or 'none'}."
            )

        return FraudJudgeVerdict(
            outcome=str(outcome),
            expected_control_ids=expected_control_ids,
            triggered_control_ids=list(triggered),
            missing_control_ids=missing,
            investigator_summary=summary,
            control_gap_detected=gap,
            remediation_hints=[f"Tune or enable {cid}" for cid in missing[:3]],
        )

    def _llm_summary(
        self,
        payload: Dict[str, Any],
        sandbox_response: Dict[str, Any],
        expected: List[str],
        triggered: List[str],
        missing: List[str],
    ) -> Optional[str]:
        llm = get_llm()
        if llm is None:
            return None
        system = "Act as a senior fraud investigator reviewing a payment authorization decision."
        user = (
            "Why did the expected control not trigger?\n"
            f"Transaction: {json.dumps(payload, default=str)[:2000]}\n"
            f"Sandbox: {json.dumps(sandbox_response, default=str)[:2000]}\n"
            f"Expected controls: {expected}\n"
            f"Triggered controls: {triggered}\n"
            f"Missing controls: {missing}\n"
            "Provide a concise investigator verdict."
        )
        return invoke_text(llm, system, user)
