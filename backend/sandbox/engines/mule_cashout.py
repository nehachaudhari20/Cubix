"""Mule / Cash-out Engine — STG-0010 lifecycle stage."""

from typing import Any, Dict, List

from ..state import SandboxState


class MuleCashoutEngine:
    """Detect mule recruitment and rapid cash-out patterns."""

    def __init__(self, state: SandboxState):
        self.state = state

    def evaluate(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        customer_id = transaction.get("customer_id")
        amount = float(transaction.get("amount") or 0)

        genai = transaction.get("genai_features") or transaction.get("genai_context") or {}
        if genai.get("mule_recruitment_score", 0) >= 0.60:
            flags.append("mule_genai_recruitment")

        if customer_id:
            customer = self.state.get_customer(customer_id)
            if customer:
                if customer.account_age_days < 14 and amount > 50_000:
                    flags.append("mule_young_account_cashout")
                if customer.get_tx_count_24h() >= 4 and amount > 100_000:
                    flags.append("mule_rapid_cashout")

        status = "FAIL" if len(flags) >= 2 else "PASS"
        return {
            "status": status,
            "stage": "STG-0010",
            "engine": "mule",
            "flags": flags,
        }
