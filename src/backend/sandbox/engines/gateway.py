"""Gateway / Processor Engine — STG-0003 lifecycle stage."""

from typing import Any, Dict, List

from ..state import SandboxState


class GatewayEngine:
    """Validates API routing, velocity, and webhook integrity at the gateway."""

    def __init__(self, state: SandboxState):
        self.state = state

    def process(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        flags: List[str] = []
        amount = float(transaction.get("amount") or 0)
        rail = (transaction.get("payment_rail") or "upi").lower()

        if amount > 500_000:
            flags.append("gateway_high_value")
        if rail in ("crypto", "wallet") and amount > 100_000:
            flags.append("gateway_rail_risk")

        if transaction.get("webhook_spoof") or transaction.get("api_manipulation"):
            flags.append("gateway_webhook_anomaly")

        customer_id = transaction.get("customer_id")
        if customer_id:
            customer = self.state.get_customer(customer_id)
            if customer and customer.get_tx_count_1h() > 8:
                flags.append("gateway_velocity_burst")

        status = "FAIL" if "gateway_webhook_anomaly" in flags else "PASS"
        return {
            "status": status,
            "stage": "STG-0003",
            "engine": "gateway",
            "flags": flags,
            "rail": rail,
        }
