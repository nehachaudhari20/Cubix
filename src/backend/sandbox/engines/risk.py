"""Risk Scoring Engine with Rules + ML Model (KB-Connected)"""

from typing import Dict, Any
from ..state import SandboxState
from ..rules import AmountRules, VelocityRules, DeviceRules, MerchantRules


class RiskEngine:
    """Risk scoring engine with rules + ML model."""
    
    def __init__(self, state: SandboxState):
        self.state = state
        self.ml_model = None
        
        # Initialize rule engines (they now fetch from KB)
        self.amount_rules = AmountRules()
        self.velocity_rules = VelocityRules()
        self.device_rules = DeviceRules()
        self.merchant_rules = MerchantRules()
    
    def set_ml_model(self, model):
        """Inject the ML model (FraudShield)."""
        self.ml_model = model
    
    def score(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate risk score for a transaction."""
        # Extract features
        features = {
            "amount": transaction.get("amount", 0),
            "customer_id": transaction.get("customer_id"),
            "device_id": transaction.get("device_id"),
            "is_new_device": transaction.get("is_new_device", True),
            "is_unknown_device": transaction.get("is_unknown_device", False),
            "device_age_days": transaction.get("device_age_days", 0),
            "merchant_risk": transaction.get("merchant_risk_score", 0.3),
            "merchant_id": transaction.get("merchant_id"),
            "customer": self.state.get_customer(transaction.get("customer_id"))
        }
        
        # 1. Apply static rules (now dynamic from KB)
        rule_risk = 0.0
        rule_results = []
        
        amount_result = self.amount_rules.evaluate(features)
        rule_results.append(amount_result)
        rule_risk += amount_result.get("risk_contribution", 0)
        
        velocity_result = self.velocity_rules.evaluate(features)
        rule_results.append(velocity_result)
        rule_risk += velocity_result.get("risk_contribution", 0)
        
        device_result = self.device_rules.evaluate(features)
        rule_results.append(device_result)
        rule_risk += device_result.get("risk_contribution", 0)
        
        merchant_result = self.merchant_rules.evaluate(features)
        rule_results.append(merchant_result)
        rule_risk += merchant_result.get("risk_contribution", 0)
        
        # Normalize rule risk (cap at 1.0)
        rule_risk = min(1.0, rule_risk)
        
        # 2. ML model score (if available)
        ml_score = 0.3
        if self.ml_model:
            try:
                ml_score = self.ml_model.predict_proba([[
                    features["amount"] / 1000,
                    features["device_age_days"],
                    int(features["is_new_device"]),
                    features["merchant_risk"]
                ]])[0][1]
            except Exception:
                pass
        
        # 3. Combined risk (weighted average)
        combined_risk = min(0.95, rule_risk * 0.5 + ml_score * 0.5)
        
        return {
            "risk_score": round(combined_risk, 3),
            "rule_risk": round(rule_risk, 3),
            "ml_score": round(ml_score, 3),
            "features": features,
            "rule_details": rule_results
        }