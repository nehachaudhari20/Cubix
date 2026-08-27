"""Authorization Engine — Final Decision (thresholds from KB parameter_bindings)."""

from typing import Dict, Any, Optional

from ..state import SandboxState
from ..rules.compiled_controls import CompiledControlSet
from ..rules.rule_engine import RuleEngine


class AuthorizationEngine:
    """Final authorization decision engine."""

    def __init__(
        self,
        state: SandboxState,
        compiled_controls: Optional[CompiledControlSet] = None,
    ):
        self.state = state
        self.compiled_controls = compiled_controls
        self._resolver = RuleEngine(rules=[], compiled_controls=compiled_controls)

    def authorize(self, risk_result: Dict[str, Any], transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Make final ALLOW/BLOCK/CHALLENGE decision."""
        risk_score = risk_result.get("risk_score", 0.5)

        allow_threshold = self._resolver.resolve_threshold(
            "allow_threshold", "authorization", 0.30
        )
        challenge_threshold = self._resolver.resolve_threshold(
            "challenge_threshold", "authorization", 0.60
        )

        if risk_score < allow_threshold:
            decision = "ALLOW"
            reason = "low_risk"
        elif risk_score < challenge_threshold:
            decision = "CHALLENGE"
            reason = "medium_risk_step_up"
        else:
            decision = "BLOCK"
            reason = "high_risk"

        customer_id = transaction.get("customer_id")
        if customer_id:
            customer = self.state.get_customer(customer_id)
            if customer:
                velocity_limit = self._resolver.resolve_threshold(
                    "velocity_limit_24h", "authorization", 5
                )
                if customer.get_tx_count_24h() >= velocity_limit:
                    decision = "BLOCK"
                    reason = "velocity_exceeded"

        return {
            "decision": decision,
            "reason": reason,
            "risk_score": risk_score,
            "thresholds_applied": {
                "allow": allow_threshold,
                "challenge": challenge_threshold,
            },
            "control_gaps": risk_result.get("control_gaps"),
        }
