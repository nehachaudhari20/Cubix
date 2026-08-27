"""Payment Initiation Engine — validates payment intent before risk scoring."""

from typing import Any, Dict, List

from ..state import SandboxState


VALID_RAILS = {"upi", "card", "bank_transfer", "wallet", "crypto", "neft", "imps", "rtgs"}


class PaymentInitiationEngine:
    """Validates payment requests and builds transaction context."""

    def __init__(self, state: SandboxState):
        self.state = state

    def validate(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Validate payer, amount, rail, merchant, and beneficiary."""
        errors: List[str] = []
        flags: List[str] = []

        customer_id = transaction.get("customer_id")
        amount = transaction.get("amount", 0)
        payment_rail = (transaction.get("payment_rail") or "upi").lower()

        customer = self.state.get_customer(customer_id) if customer_id else None
        if not customer:
            return {
                "status": "FAIL",
                "reason": "payer_not_found",
                "message": "Payer customer not found",
                "errors": ["payer_not_found"],
            }

        if amount is None or amount <= 0:
            errors.append("invalid_amount")

        if payment_rail not in VALID_RAILS:
            errors.append(f"unsupported_rail:{payment_rail}")

        account_id = transaction.get("account_id")
        if account_id:
            account = self.state.get_account(account_id)
            if not account:
                errors.append("account_not_found")
            elif account.customer_id != customer_id:
                errors.append("account_customer_mismatch")
            elif not account.is_active:
                errors.append("account_inactive")
            elif amount and amount > account.daily_limit:
                errors.append("exceeds_daily_limit")

        merchant_id = transaction.get("merchant_id")
        merchant_risk = transaction.get("merchant_risk_score", 0.3)
        if merchant_id:
            merchant = self.state.get_merchant(merchant_id)
            if not merchant:
                errors.append("merchant_not_found")
            elif not merchant.is_active:
                errors.append("merchant_inactive")
            elif not merchant.kyb_verified:
                flags.append("merchant_kyb_unverified")
            else:
                merchant_risk = merchant.risk_score
                if merchant.declared_mcc != merchant.mcc:
                    flags.append("mcc_misrepresentation")
                transaction["merchant_mcc"] = merchant.mcc
                transaction["merchant_declared_mcc"] = merchant.declared_mcc

        beneficiary_id = transaction.get("beneficiary_id")
        if beneficiary_id:
            beneficiary = self.state.get_beneficiary(beneficiary_id)
            if not beneficiary:
                errors.append("beneficiary_not_found")
            elif not beneficiary.is_verified:
                flags.append("beneficiary_unverified")
            else:
                transaction["beneficiary_risk_score"] = beneficiary.risk_score

        if errors:
            return {
                "status": "FAIL",
                "reason": errors[0],
                "message": f"Payment initiation failed: {', '.join(errors)}",
                "errors": errors,
                "flags": flags,
            }

        transaction["merchant_risk_score"] = merchant_risk

        return {
            "status": "PASS",
            "reason": "payment_intent_valid",
            "message": "Payment intent validated",
            "amount": amount,
            "payment_rail": payment_rail,
            "merchant_risk_score": merchant_risk,
            "flags": flags,
            "payer_id": customer_id,
        }
