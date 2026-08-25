"""Risk Scoring Engine with Rules + ML Model + Anomaly (KB-Connected)"""



from typing import Dict, Any, Optional



from ..state import SandboxState

from ..rules.compiled_controls import CompiledControlSet

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

    """Risk scoring engine with rules + FraudShield + isolation forest."""



    def __init__(

        self,

        state: SandboxState,

        compiled_controls: Optional[CompiledControlSet] = None,

    ):

        self.state = state

        self.compiled_controls = compiled_controls

        self.ml_model = None

        self.anomaly_scorer = None

        self.risk_blend_spec: Optional[Dict[str, Any]] = None



        self.amount_rules = AmountRules(compiled_controls=compiled_controls)

        self.velocity_rules = VelocityRules(compiled_controls=compiled_controls)

        self.device_rules = DeviceRules(compiled_controls=compiled_controls)

        self.merchant_rules = MerchantRules(compiled_controls=compiled_controls)

        self.identity_rules = IdentityRules(compiled_controls=compiled_controls)

        self.aml_rules = AMLRules(compiled_controls=compiled_controls)

        self.mule_rules = MuleRules(compiled_controls=compiled_controls)



    def set_ml_model(self, model):

        """Inject the ML model (FraudShield)."""

        self.ml_model = model

        if hasattr(model, "spec"):

            self.risk_blend_spec = getattr(model, "spec", None)



    def set_anomaly_scorer(self, scorer):

        """Inject isolation-forest anomaly scorer."""

        self.anomaly_scorer = scorer



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

        genai_features = transaction.get("genai_context") or transaction.get("genai_features") or {}
        genai_risk = 0.0
        if genai_features:
            from .genai_context import GenAIContextEngine
            genai_eval = GenAIContextEngine().evaluate({
                "genai_features": genai_features,
                "attack_family": transaction.get("attack_family") or transaction.get("family_id"),
                "variant_id": transaction.get("variant_id"),
                "channels": transaction.get("channels"),
                "victim_coerced": transaction.get("victim_coerced"),
                "capability_ids": transaction.get("capability_ids") or [],
            }, sandbox_state=self.state)
            genai_risk = float(genai_eval.get("genai_risk_contribution") or 0)
            rule_results.append({
                "rule_set": "genai_context",
                "risk_contribution": round(genai_risk * 0.4, 4),
                "triggered_rules": genai_eval.get("triggered_rules") or [],
            })
            rule_risk = min(1.0, rule_risk + genai_risk * 0.35)

        ml_score = 0.3

        if self.ml_model:

            try:

                if hasattr(self.ml_model, "predict_proba_from_transaction"):

                    ml_score = self.ml_model.predict_proba_from_transaction(

                        transaction, self.state

                    )

                else:

                    ml_score = self.ml_model.predict_proba([[

                        features["amount"] / 1000,

                        features["device_age_days"],

                        int(features["is_new_device"]),

                        features["merchant_risk"],

                    ]])[0][1]

            except Exception:

                pass



        anomaly_score = 0.0

        if self.anomaly_scorer:

            try:

                anomaly_score = self.anomaly_scorer.score_transaction(

                    transaction, self.state

                )

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



        return {

            "risk_score": combined_risk,

            "rule_risk": round(rule_risk, 3),

            "ml_score": round(ml_score, 3),

            "anomaly_score": round(anomaly_score, 3),

            "genai_risk": round(genai_risk, 3),

            "features": features,

            "rule_details": rule_results,

        }


