"""Beneficiary Check Engine — STG-0007 lifecycle stage."""

from typing import Any, Dict, List

from ..state import SandboxState


class BeneficiaryCheckEngine:
    """Validates beneficiary linkage patterns at payment time."""

    def __init__(self, state: SandboxState):
        self.state = state

    def check(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        customer_id = transaction.get("customer_id")
        beneficiary_id = transaction.get("beneficiary_id")

        if beneficiary_id:
            beneficiary = self.state.get_beneficiary(beneficiary_id)
            if not beneficiary:
                flags.append("beneficiary_unknown")
            elif beneficiary.customer_id != customer_id:
                flags.append("beneficiary_customer_mismatch")
            elif beneficiary.is_new:
                flags.append("new_beneficiary")
                transaction["is_new_beneficiary"] = True

        if customer_id:
            recent = [
                b for b in self.state.beneficiaries.values()
                if b.customer_id == customer_id
            ]
            transaction["distinct_beneficiaries_last_24h"] = len(recent)
            if len(recent) > 5:
                flags.append("beneficiary_velocity")

        status = "FAIL" if "beneficiary_customer_mismatch" in flags else "PASS"
        return {
            "status": status,
            "stage": "STG-0007",
            "engine": "beneficiary",
            "flags": flags,
        }
