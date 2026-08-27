"""Account and Merchant Onboarding Engine"""

from datetime import datetime
from typing import Any, Dict

from ..state import SandboxState, SyntheticMerchant, SyntheticAccount


# High-risk MCC codes (gambling, crypto, etc.)
HIGH_RISK_MCCS = {"7995", "6012", "6051", "6211"}


class AccountMerchantEngine:
    """Manages account creation, merchant KYB, and MCC assignment."""

    def __init__(self, state: SandboxState):
        self.state = state

    def onboard_merchant(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Register a merchant with MCC and KYB status."""
        merchant_id = payload.get("merchant_id")
        if not merchant_id:
            return {"status": "FAIL", "reason": "missing_merchant_id", "message": "merchant_id is required"}

        if self.state.get_merchant(merchant_id):
            return {"status": "FAIL", "reason": "merchant_already_exists", "message": f"Merchant {merchant_id} exists"}

        mcc = str(payload.get("mcc", "5411"))
        declared_mcc = str(payload.get("declared_mcc", mcc))
        kyb_verified = bool(payload.get("kyb_verified", True))

        base_risk = float(payload.get("risk_score", 0.3))
        if mcc in HIGH_RISK_MCCS:
            base_risk = max(base_risk, 0.7)
        if declared_mcc != mcc:
            base_risk = max(base_risk, 0.75)

        merchant = SyntheticMerchant(
            merchant_id=merchant_id,
            name=payload.get("name", "Synthetic Merchant"),
            mcc=mcc,
            declared_mcc=declared_mcc,
            risk_score=base_risk,
            kyb_verified=kyb_verified,
            created_at=datetime.now(),
            owner_customer_id=payload.get("owner_customer_id"),
            is_active=payload.get("is_active", True),
        )
        self.state.merchants[merchant_id] = merchant

        flags = []
        if declared_mcc != mcc:
            flags.append("mcc_misrepresentation")
        if not kyb_verified:
            flags.append("kyb_unverified")
        if mcc in HIGH_RISK_MCCS:
            flags.append("high_risk_mcc")

        return {
            "status": "PASS",
            "merchant_id": merchant_id,
            "mcc": mcc,
            "declared_mcc": declared_mcc,
            "risk_score": base_risk,
            "kyb_verified": kyb_verified,
            "flags": flags,
            "message": f"Merchant {merchant_id} onboarded",
        }

    def open_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Open a synthetic account for a customer."""
        account_id = payload.get("account_id")
        customer_id = payload.get("customer_id")

        if not account_id or not customer_id:
            return {"status": "FAIL", "reason": "missing_fields", "message": "account_id and customer_id required"}

        if not self.state.get_customer(customer_id):
            return {"status": "FAIL", "reason": "customer_not_found", "message": f"Customer {customer_id} not found"}

        if self.state.get_account(account_id):
            return {"status": "FAIL", "reason": "account_already_exists", "message": f"Account {account_id} exists"}

        account = SyntheticAccount(
            account_id=account_id,
            customer_id=customer_id,
            balance=float(payload.get("balance", 50000.0)),
            created_at=datetime.now(),
            daily_limit=float(payload.get("daily_limit", 100000.0)),
            monthly_limit=float(payload.get("monthly_limit", 1000000.0)),
        )
        self.state.accounts[account_id] = account

        return {
            "status": "PASS",
            "account_id": account_id,
            "customer_id": customer_id,
            "balance": account.balance,
            "message": f"Account {account_id} opened",
        }

    def link_beneficiary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Link a payee/beneficiary to a customer."""
        from ..state import SyntheticBeneficiary

        beneficiary_id = payload.get("beneficiary_id")
        customer_id = payload.get("customer_id")

        if not beneficiary_id or not customer_id:
            return {"status": "FAIL", "reason": "missing_fields", "message": "beneficiary_id and customer_id required"}

        if not self.state.get_customer(customer_id):
            return {"status": "FAIL", "reason": "customer_not_found", "message": f"Customer {customer_id} not found"}

        if self.state.get_beneficiary(beneficiary_id):
            return {"status": "FAIL", "reason": "beneficiary_already_exists", "message": f"Beneficiary {beneficiary_id} exists"}

        beneficiary = SyntheticBeneficiary(
            beneficiary_id=beneficiary_id,
            customer_id=customer_id,
            name=payload.get("name", "Synthetic Beneficiary"),
            account_ref=payload.get("account_ref", f"ACC-{beneficiary_id}"),
            created_at=datetime.now(),
            is_verified=bool(payload.get("is_verified", True)),
            risk_score=float(payload.get("risk_score", 0.2)),
        )
        self.state.beneficiaries[beneficiary_id] = beneficiary

        return {
            "status": "PASS",
            "beneficiary_id": beneficiary_id,
            "customer_id": customer_id,
            "risk_score": beneficiary.risk_score,
            "message": f"Beneficiary {beneficiary_id} linked to {customer_id}",
        }
