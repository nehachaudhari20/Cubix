"""Risk Scoring Engine with Rules + ML Model (KB-Connected)"""

from typing import Dict, Any
from ..state import SandboxState
from ..rules import (
    AmountRules,
    VelocityRules,
    DeviceRules,
    MerchantRules,
    IdentityRules,
    AMLRules,
    MuleRules,
)


class RiskEngine:
    """Risk scoring engine with rules + ML model."""

    def __init__(self, state: SandboxState):
        self.state = state
        self.ml_model = None

        self.amount_rules = AmountRules()
        self.velocity_rules = VelocityRules()
        self.device_rules = DeviceRules()
        self.merchant_rules = MerchantRules()
        self.identity_rules = IdentityRules()
        self.aml_rules = AMLRules()
        self.mule_rules = MuleRules()

    def set_ml_model(self, model):
        """Inject the ML model (FraudShield)."""
        self.ml_model = model

    def score(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate risk score for a transaction."""
        customer_id = transaction.get("customer_id")
        beneficiary_id = transaction.get("beneficiary_id")

        features = {
            "amount": transaction.get("amount", 0),
            "customer_id": customer_id,
            "device_id": transaction.get("device_id"),
            "beneficiary_id": beneficiary_id,
            "is_new_device": transaction.get("is_new_device", True),
            "is_unknown_device": transaction.get("is_unknown_device", False),
            "device_age_days": transaction.get("device_age_days", 0),
            "merchant_risk": transaction.get("merchant_risk_score", 0.3),
            "merchant_id": transaction.get("merchant_id"),
            "customer": self.state.get_customer(customer_id),
            "beneficiary": self.state.get_beneficiary(beneficiary_id) if beneficiary_id else None,
            "state": self.state,
            "payment_flags": transaction.get("payment_initiation_flags", []),
        }

        rule_risk = 0.0
        rule_results = []

        for rule_engine in (
            self.identity_rules,
            self.amount_rules,
            self.velocity_rules,
            self.device_rules,
            self.merchant_rules,
            self.aml_rules,
            self.mule_rules,
        ):
            result = rule_engine.evaluate(features)
            rule_results.append(result)
            rule_risk += result.get("risk_contribution", 0)

        rule_risk = min(1.0, rule_risk)

        ml_score = 0.3
        if self.ml_model:
            try:
                if hasattr(self.ml_model, "predict_proba_from_transaction"):
                    ml_score = self.ml_model.predict_proba_from_transaction(
                        transaction, self.state
                    )
                else:
                    # Legacy sklearn-style 4-feature fallback
                    ml_score = self.ml_model.predict_proba([[
                        features["amount"] / 1000,
                        features["device_age_days"],
                        int(features["is_new_device"]),
                        features["merchant_risk"],
                    ]])[0][1]
            except Exception:
                pass

        combined_risk = min(0.95, rule_risk * 0.5 + ml_score * 0.5)

        return {
            "risk_score": round(combined_risk, 3),
            "rule_risk": round(rule_risk, 3),
            "ml_score": round(ml_score, 3),
            "features": features,
            "rule_details": rule_results,
        }
