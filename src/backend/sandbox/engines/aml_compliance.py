"""AML / Compliance Engine — STG-0009 lifecycle stage."""

from typing import Any, Dict, List

from ..state import SandboxState


class AMLComplianceEngine:
    """AML screening, structuring detection, and sanctions proxy checks."""

    def __init__(self, state: SandboxState):
        self.state = state

    def screen(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        amount = float(transaction.get("amount") or 0)
        customer_id = transaction.get("customer_id")

        if 49000 <= amount <= 49999:
            flags.append("aml_structuring_proxy")
        if amount >= 1_000_000:
            flags.append("aml_high_value_reporting")

        genai = transaction.get("genai_features") or transaction.get("genai_context") or {}
        if genai.get("adaptive_evasion_score", 0) >= 0.65:
            flags.append("aml_adaptive_evasion")
        if genai.get("model_evasion_score", 0) >= 0.60:
            flags.append("aml_model_evasion")

        if customer_id:
            customer = self.state.get_customer(customer_id)
            if customer and customer.trust_score < 0.35:
                flags.append("aml_low_trust_customer")

        risk = min(1.0, len(flags) * 0.22 + (0.15 if flags else 0))
        status = "FAIL" if "aml_adaptive_evasion" in flags and amount > 200_000 else "PASS"
        return {
            "status": status,
            "stage": "STG-0009",
            "engine": "aml",
            "flags": flags,
            "aml_risk": round(risk, 4),
        }
