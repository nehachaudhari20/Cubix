"""
Evidence Collector — converts Red Team sandbox runs into Blue Team training evidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH
from .features import FeatureBuilder
from .schemas import EvidenceRecord


class EvidenceCollector:
    """Collects sandbox observations from Red Team campaigns into the adversarial buffer."""

    PAYMENT_ACTION = "initiate_payment"

    def __init__(
        self,
        buffer: Optional[EvidenceBuffer] = None,
        feature_builder: Optional[FeatureBuilder] = None,
        enabled: bool = True,
    ):
        self.buffer = buffer or EvidenceBuffer()
        self.feature_builder = feature_builder or FeatureBuilder()
        self.enabled = enabled

    def _field(self, obj: Any, name: str, default=None):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    def collect(
        self,
        sandbox_response: Dict[str, Any],
        payload: Any,
        plan: Any,
        hypothesis: Any,
        analysis: Any,
        sandbox: Any,
    ) -> Optional[EvidenceRecord]:
        """
        Store one observation from a Red Team step.

        Only payment actions are stored for ML retraining (FeatureBuilder is
        transaction-scoped). Setup steps are skipped.
        """
        if not self.enabled:
            return None

        action_type = self._field(payload, "action_type")
        if action_type != self.PAYMENT_ACTION:
            return None

        action_payload = self._field(payload, "action_payload") or {}
        state = sandbox.get_state() if sandbox and hasattr(sandbox, "get_state") else None

        features = self.feature_builder.build(action_payload, state) if state else {}

        sandbox_state = sandbox_response.get("state") or {}
        control_triggers = sandbox_response.get("control_triggers") or sandbox_state.get("control_triggers") or []

        decision = sandbox_response.get("decision", "UNKNOWN")
        label = self._infer_label(decision, analysis)
        evasion = self._evasion_outcome(decision)

        record = EvidenceRecord(
            evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
            campaign_id=self._field(payload, "campaign_id", "unknown"),
            attack_family=self._field(plan, "primary_family", "unknown"),
            attack_variant=self._field(payload, "attack_variant"),
            action_type=action_type,
            sandbox_decision=decision,
            evasion_outcome=evasion,
            analysis_outcome=self._field(analysis, "outcome"),
            blocking_control=self._field(analysis, "blocking_control"),
            control_triggers=control_triggers,
            ml_score=sandbox_state.get("ml_score") or sandbox_response.get("ml_score"),
            rule_risk=sandbox_state.get("rule_risk") or sandbox_response.get("rule_risk"),
            risk_score=sandbox_state.get("risk_score") or sandbox_response.get("risk_score"),
            label=label,
            features=features,
            amount=action_payload.get("amount"),
            step=self._field(payload, "step"),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="red_team",
        )
        return self.buffer.append(record)

    def _infer_label(self, decision: str, analysis: Any) -> int:
        """
        Red Team payment steps are adversarial fraud attempts → label=1.

        Even if blocked/challenged, the transaction intent is fraudulent.
        """
        return 1

    def _evasion_outcome(self, decision: str) -> str:
        if decision == "ALLOW":
            return "bypassed"
        if decision == "CHALLENGE":
            return "challenged"
        if decision == "BLOCK":
            return "blocked"
        return "unknown"

    @classmethod
    def from_env(cls) -> "EvidenceCollector":
        import os
        enabled = os.environ.get("EVIDENCE_BUFFER_ENABLED", "true").lower() in ("1", "true", "yes")
        path = os.environ.get("EVIDENCE_BUFFER_PATH", DEFAULT_BUFFER_PATH)
        return cls(buffer=EvidenceBuffer(path), enabled=enabled)
