"""
Evidence Collector — converts Red Team sandbox runs into Blue Team training evidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH
from .features import FeatureBuilder
from .schemas import ACTION_SURFACE, TRAINABLE_ACTION_TYPES, EvidenceRecord


class EvidenceCollector:
    """Collects sandbox observations from Red Team campaigns into the adversarial buffer."""

    PAYMENT_ACTION = "initiate_payment"
    TRAINABLE_ACTIONS = TRAINABLE_ACTION_TYPES

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

        Any action that adjudicates a control surface is stored (payment, agent
        context, social engineering, KYC evidence, consent). Pure setup steps
        (register_customer, register_device, open_account, ...) are skipped —
        they mutate world state but no control decides on them.
        """
        if not self.enabled:
            return None

        action_type = self._field(payload, "action_type")
        if action_type not in self.TRAINABLE_ACTIONS:
            return None

        action_payload = self._field(payload, "action_payload") or {}
        state = sandbox.get_state() if sandbox and hasattr(sandbox, "get_state") else None

        sandbox_state = sandbox_response.get("state") or {}
        state_snapshot = sandbox_response.get("state_snapshot") or {}
        features = self._build_features(action_type, action_payload, state, state_snapshot)

        control_triggers = sandbox_response.get("control_triggers") or sandbox_state.get("control_triggers") or []

        decision = sandbox_response.get("decision", "UNKNOWN")
        label = self._infer_label(decision, analysis, payload, action_payload)
        evasion = self._evasion_outcome(decision)

        record = EvidenceRecord(
            evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
            campaign_id=self._field(payload, "campaign_id", "unknown"),
            attack_family=self._field(plan, "primary_family", "unknown"),
            attack_variant=self._field(payload, "attack_variant"),
            action_type=action_type,
            surface=ACTION_SURFACE.get(action_type, "payment"),
            scenario_type=(
                action_payload.get("entry_point")
                or self._field(plan, "entry_point")
            ),
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
            is_hard_negative=bool(action_payload.get("is_hard_negative")),
            legitimacy_reason=action_payload.get("legitimacy_reason"),
        )
        return self.buffer.append(record)

    def _build_features(
        self,
        action_type: str,
        action_payload: Dict[str, Any],
        state: Any,
        state_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Payment rows use the transaction feature builder; other surfaces use
        the control-surface builder, which fills payment features with defaults
        and carries the surface's own signals (GenAI scores, control flags)."""
        if action_type == self.PAYMENT_ACTION:
            return self.feature_builder.build(action_payload, state) if state else {}
        return self.feature_builder.build_control_surface(
            action_type,
            action_payload,
            state,
            state_snapshot,
        )

    def _infer_label(
        self,
        decision: str,
        analysis: Any,
        payload: Any = None,
        action_payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Red Team steps are adversarial attempts → label=1, even when blocked:
        the *intent* is fraudulent regardless of whether the control caught it.

        Exception: steps explicitly marked as suspicious-but-legitimate probes
        (hard negatives) are label=0, so the model learns where the boundary is
        instead of treating every unusual pattern as fraud.
        """
        action_payload = action_payload or {}
        if action_payload.get("is_hard_negative") or action_payload.get("is_legitimate"):
            return 0
        if self._field(payload, "is_hard_negative"):
            return 0
        if self._field(analysis, "outcome") == "legitimate_suspicious":
            return 0
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
