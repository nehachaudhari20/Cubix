"""Control Gap Lab — compare sandbox triggers vs KB expected controls."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.red_team.deepteam.fraud_judge import FraudInvestigatorJudge
from backend.red_team.deepteam.schemas import FraudJudgeVerdict


class ControlGapLab:
    """Post-execution analysis: did expected KB controls fire?"""

    def __init__(self):
        self.judge = FraudInvestigatorJudge()
        self.findings: List[FraudJudgeVerdict] = []

    def analyze(
        self,
        *,
        payload: Dict[str, Any],
        sandbox_response: Dict[str, Any],
        family: Optional[Dict[str, Any]] = None,
    ) -> FraudJudgeVerdict:
        expected = list((family or {}).get("targeted_control_ids") or [])
        verdict = self.judge.evaluate(
            payload=payload,
            sandbox_response=sandbox_response,
            expected_control_ids=expected,
            triggered_control_ids=sandbox_response.get("control_triggers") or [],
        )
        if verdict.control_gap_detected or verdict.missing_control_ids:
            self.findings.append(verdict)
        return verdict

    def summarize(self) -> Dict[str, Any]:
        gaps = [item for item in self.findings if item.control_gap_detected]
        return {
            "total_findings": len(self.findings),
            "control_gaps": len(gaps),
            "families_with_gaps": len({item.outcome for item in gaps}),
            "recent_missing_controls": [
                cid
                for item in self.findings[-5:]
                for cid in item.missing_control_ids
            ],
        }
