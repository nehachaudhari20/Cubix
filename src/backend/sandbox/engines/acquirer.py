"""Acquirer Engine — STG-0015..0018 merchant/acquirer lifecycle stages."""

from typing import Any, Dict, List

from ..state import SandboxState


class AcquirerEngine:
    """Acquirer onboarding, MCC, and portfolio monitoring checks."""

    def __init__(self, state: SandboxState):
        self.state = state

    def monitor(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        merchant_id = transaction.get("merchant_id")

        if not merchant_id:
            return {
                "status": "PASS",
                "stage": "STG-0015",
                "engine": "acquirer",
                "flags": [],
                "skipped": True,
            }

        merchant = self.state.get_merchant(merchant_id)
        if not merchant:
            flags.append("acquirer_merchant_unknown")
        else:
            if merchant.declared_mcc and merchant.mcc != merchant.declared_mcc:
                flags.append("acquirer_mcc_mismatch")
            if merchant.risk_score >= 0.75:
                flags.append("acquirer_high_risk_merchant")
            if not merchant.kyb_verified:
                flags.append("acquirer_kyb_unverified")

        status = "FAIL" if "acquirer_mcc_mismatch" in flags else "PASS"
        return {
            "status": status,
            "stage": "STG-0016",
            "engine": "acquirer",
            "flags": flags,
            "merchant_risk_score": getattr(merchant, "risk_score", transaction.get("merchant_risk_score")),
        }
