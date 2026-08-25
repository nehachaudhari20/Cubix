"""Risk Scoring Engine — data-driven RuleEngine + ML + anomaly + GenAI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..state import SandboxState
from ..rules.compiled_controls import CompiledControlSet
from ..rules.rule_engine import RuleEngine
from ..rules.feature_context import build_rule_context


class RiskEngine:
    """Risk scoring with KB RuleEngine + FraudShield + isolation forest."""

    def __init__(
        self,
        state: SandboxState,
        compiled_controls: Optional[CompiledControlSet] = None,
        rule_engine: Optional[RuleEngine] = None,
    ):
        self.state = state
        self.compiled_controls = compiled_controls
        self.ml_model = None
        self.anomaly_scorer = None
        self.risk_blend_spec: Optional[Dict[str, Any]] = None
        self.rule_engine = rule_engine or RuleEngine(compiled_controls=compiled_controls)

    def set_ml_model(self, model) -> None:
        self.ml_model = model
        if hasattr(model, "spec"):
            self.risk_blend_spec = getattr(model, "spec", None)

    def set_anomaly_scorer(self, scorer) -> None:
        self.anomaly_scorer = scorer

    def score(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate risk score for a transaction via KB-driven rules."""
        journey = transaction.get("journey") or []
        prior_triggers = transaction.get("control_triggers") or transaction.get("payment_initiation_flags") or []

        family = None
        family_id = transaction.get("attack_family") or transaction.get("family_id")
        # Optional: caller may pass family dict for expected controls / signals
        if isinstance(transaction.get("family"), dict):
            family = transaction["family"]

        context = build_rule_context(
            transaction,
            self.state,
            journey=journey,
            control_triggers=prior_triggers,
            family=family,
        )

        # Ensure family signals/controls from transaction hints
        if family_id and not context.get("family_signal_ids"):
            context["signal_context_active"] = True

        expected = list(
            transaction.get("expected_controls")
            or transaction.get("targeted_control_ids")
            or context.get("expected_controls")
            or []
        )

        rule_result = self.rule_engine.evaluate(context, expected_controls=expected)
        rule_risk = float(rule_result.risk_contribution)
        rule_details = list(rule_result.rule_details)

        # GenAI blend (still via GenAI engine)
        genai_features = transaction.get("genai_context") or transaction.get("genai_features") or {}
        genai_risk = 0.0
        if genai_features:
            from .genai_context import GenAIContextEngine

            genai_eval = GenAIContextEngine().evaluate(
                {
                    "genai_features": genai_features,
                    "attack_family": family_id,
                    "variant_id": transaction.get("variant_id"),
                    "channels": transaction.get("channels"),
                    "victim_coerced": transaction.get("victim_coerced"),
                    "capability_ids": transaction.get("capability_ids") or [],
                },
                sandbox_state=self.state,
            )
            genai_risk = float(genai_eval.get("genai_risk_contribution") or 0)
            rule_details.append(
                {
                    "rule_set": "genai_context",
                    "risk_contribution": round(genai_risk * 0.4, 4),
                    "triggered_rules": genai_eval.get("triggered_rules") or [],
                }
            )
            rule_risk = min(1.0, rule_risk + genai_risk * 0.35)

        # Control-gap risk bump: expected controls that never fired
        gaps = rule_result.control_gaps
        if gaps.get("has_gap"):
            gap_bump = min(0.25, 0.05 * int(gaps.get("gap_count") or 0))
            rule_risk = min(1.0, rule_risk + gap_bump)
            rule_details.append(
                {
                    "rule_set": "control_gap",
                    "risk_contribution": round(gap_bump, 4),
                    "triggered_rules": [f"gap_{c}" for c in gaps.get("missing_controls") or []],
                    "control_gaps": gaps,
                }
            )

        ml_score = 0.3
        if self.ml_model:
            try:
                if hasattr(self.ml_model, "predict_proba_from_transaction"):
                    ml_score = self.ml_model.predict_proba_from_transaction(
                        transaction, self.state
                    )
                else:
                    ml_score = self.ml_model.predict_proba(
                        [[
                            context["amount"] / 1000,
                            context["device_age_days"],
                            int(context["is_new_device"]),
                            context["merchant_risk_score"],
                        ]]
                    )[0][1]
            except Exception:
                pass

        anomaly_score = 0.0
        if self.anomaly_scorer:
            try:
                anomaly_score = self.anomaly_scorer.score_transaction(transaction, self.state)
            except Exception:
                pass

        if self.anomaly_scorer:
            try:
                from backend.blue_team.anomaly import combine_risk_scores

                combined_risk = combine_risk_scores(
                    rule_risk, ml_score, anomaly_score, spec=self.risk_blend_spec
                )
            except Exception:
                combined_risk = min(0.95, rule_risk * 0.5 + ml_score * 0.5)
        else:
            combined_risk = min(0.95, rule_risk * 0.5 + ml_score * 0.5)

        features = {
            "amount": context["amount"],
            "customer_id": context.get("customer_id"),
            "device_id": context.get("device_id"),
            "beneficiary_id": context.get("beneficiary_id"),
            "is_new_device": context["is_new_device"],
            "is_unknown_device": context["is_unknown_device"],
            "device_age_days": context["device_age_days"],
            "merchant_risk": context["merchant_risk_score"],
            "journey_correlation": {
                k: context[k]
                for k in context
                if k.startswith("journey_") or k == "engine_transition_risk"
            },
        }

        return {
            "risk_score": combined_risk,
            "rule_risk": round(rule_risk, 3),
            "ml_score": round(ml_score, 3),
            "anomaly_score": round(anomaly_score, 3),
            "genai_risk": round(genai_risk, 3),
            "features": features,
            "rule_details": rule_details,
            "triggered_rules": rule_result.triggered_rules,
            "triggered_controls": rule_result.triggered_controls,
            "triggered_signals": rule_result.triggered_signals,
            "control_gaps": gaps,
            "thresholds_used": rule_result.thresholds_used,
            "journey_features": features["journey_correlation"],
        }
