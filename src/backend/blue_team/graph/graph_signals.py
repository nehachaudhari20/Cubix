"""
Graph signal builder — sandbox state → fraud graph features (Phase 13).

Fixes stubbed velocity/graph counters in FeatureBuilder and supplies
signals for fidelity / generalization / graph-model evaluation (Phase 14).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .entity_graph import EntityGraphBuilder

GRAPH_SIGNAL_FEATURES = [
    "beneficiary_distinct_payer_count",
    "is_shared_beneficiary",
    "shared_device_customer_count",
    "graph_cluster_size",
    "mule_risk_score",
]


class GraphSignalBuilder:
    """Compute entity-graph features from sandbox transaction history."""

    SHARED_BENEFICIARY_THRESHOLD = 3

    def __init__(self, state: Any, reference_time: Optional[datetime] = None):
        self.state = state
        self.reference_time = reference_time or datetime.now()

    def build(
        self,
        transaction: Dict[str, Any],
        *,
        include_graph_extras: bool = True,
    ) -> Dict[str, Any]:
        customer_id = transaction.get("customer_id")
        device_id = transaction.get("device_id")
        beneficiary_id = transaction.get("beneficiary_id")

        distinct_ben_24h = self.distinct_beneficiaries_last_24h(customer_id)
        distinct_dev_7d = self.distinct_devices_last_7d(customer_id)
        payer_count = self.beneficiary_distinct_payer_count(beneficiary_id)
        shared_device_count = self.shared_device_customer_count(device_id)

        signals: Dict[str, Any] = {
            "distinct_beneficiaries_last_24h": distinct_ben_24h,
            "distinct_devices_last_7d": distinct_dev_7d,
        }

        if include_graph_extras:
            cluster_size = 1
            if customer_id and self.state:
                try:
                    cluster_size = EntityGraphBuilder(self.state).cluster_size(
                        EntityGraphBuilder.CUSTOMER, customer_id
                    )
                except ImportError:
                    cluster_size = max(distinct_ben_24h, shared_device_count, 1)

            is_shared = int(payer_count >= self.SHARED_BENEFICIARY_THRESHOLD)
            mule_risk = self._mule_risk_score(
                payer_count=payer_count,
                shared_device_count=shared_device_count,
                distinct_ben_24h=distinct_ben_24h,
                is_shared_beneficiary=bool(is_shared),
                cluster_size=cluster_size,
            )

            signals.update({
                "beneficiary_distinct_payer_count": payer_count,
                "is_shared_beneficiary": is_shared,
                "shared_device_customer_count": shared_device_count,
                "graph_cluster_size": cluster_size,
                "mule_risk_score": round(mule_risk, 4),
            })

        return signals

    def distinct_beneficiaries_last_24h(self, customer_id: Optional[str]) -> int:
        if not customer_id or not self.state:
            return 0
        cutoff = self.reference_time - timedelta(hours=24)
        beneficiaries: set = set()
        for tx in getattr(self.state, "transaction_log", []) or []:
            if tx.get("customer_id") != customer_id:
                continue
            ts = tx.get("timestamp")
            if ts is None or not isinstance(ts, datetime) or ts <= cutoff:
                continue
            ben = tx.get("beneficiary_id")
            if ben:
                beneficiaries.add(ben)
        return len(beneficiaries) or 0

    def distinct_devices_last_7d(self, customer_id: Optional[str]) -> int:
        if not customer_id or not self.state:
            return 0
        cutoff = self.reference_time - timedelta(days=7)
        devices: set = set()
        for tx in getattr(self.state, "transaction_log", []) or []:
            if tx.get("customer_id") != customer_id:
                continue
            ts = tx.get("timestamp")
            if ts is None or not isinstance(ts, datetime) or ts <= cutoff:
                continue
            dev = tx.get("device_id")
            if dev:
                devices.add(dev)
        return len(devices) or 0

    def beneficiary_distinct_payer_count(self, beneficiary_id: Optional[str]) -> int:
        if not beneficiary_id or not self.state:
            return 0
        if hasattr(self.state, "count_distinct_payers_to_beneficiary"):
            return self.state.count_distinct_payers_to_beneficiary(beneficiary_id)
        payers: set = set()
        for tx in getattr(self.state, "transaction_log", []) or []:
            if tx.get("beneficiary_id") == beneficiary_id and tx.get("customer_id"):
                payers.add(tx["customer_id"])
        return len(payers)

    def shared_device_customer_count(self, device_id: Optional[str]) -> int:
        if not device_id or not self.state:
            return 0
        customers: set = set()
        for tx in getattr(self.state, "transaction_log", []) or []:
            if tx.get("device_id") == device_id and tx.get("customer_id"):
                customers.add(tx["customer_id"])
        return len(customers)

    @staticmethod
    def _mule_risk_score(
        *,
        payer_count: int,
        shared_device_count: int,
        distinct_ben_24h: int,
        is_shared_beneficiary: bool,
        cluster_size: int,
    ) -> float:
        score = 0.0
        if is_shared_beneficiary:
            score += 0.35
        elif payer_count >= 2:
            score += 0.15
        if shared_device_count >= 2:
            score += 0.25
        if distinct_ben_24h >= 3:
            score += 0.20
        if cluster_size >= 4:
            score += 0.20
        return min(1.0, score)

    @classmethod
    def graph_boost(cls, features: Dict[str, Any]) -> float:
        """Post-hoc score boost for tabular+graph ablation (Phase 14)."""
        boost = 0.0
        if int(features.get("is_shared_beneficiary", 0)):
            boost += 0.12
        payer_count = int(features.get("beneficiary_distinct_payer_count", 0))
        if payer_count >= 3:
            boost += 0.08
        if int(features.get("shared_device_customer_count", 0)) >= 2:
            boost += 0.10
        if int(features.get("graph_cluster_size", 0)) >= 4:
            boost += 0.08
        mule = float(features.get("mule_risk_score", 0))
        boost += min(0.12, mule * 0.15)
        return min(0.35, boost)
