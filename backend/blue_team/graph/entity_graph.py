"""
Entity graph — customer / device / beneficiary relationships from sandbox state.

Used for cluster detection and cross-account composite attack analysis (Phase 14).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import networkx as nx
except ImportError:  # pragma: no cover
    nx = None  # type: ignore


class EntityGraphBuilder:
    """Build an undirected entity graph from SandboxState transaction history."""

    CUSTOMER = "customer"
    DEVICE = "device"
    BENEFICIARY = "beneficiary"

    def __init__(self, state: Any):
        self.state = state
        self._graph: Optional[Any] = None
        self._node_types: Dict[str, str] = {}

    def _node(self, entity_type: str, entity_id: str) -> str:
        key = f"{entity_type}:{entity_id}"
        self._node_types[key] = entity_type
        return key

    def build(self) -> Any:
        if nx is None:
            raise ImportError("networkx is required for entity graph analysis")
        if self._graph is not None:
            return self._graph

        g = nx.Graph()
        log = getattr(self.state, "transaction_log", []) or []

        device_to_customers: Dict[str, Set[str]] = defaultdict(set)
        beneficiary_to_customers: Dict[str, Set[str]] = defaultdict(set)

        for tx in log:
            customer_id = tx.get("customer_id")
            device_id = tx.get("device_id")
            beneficiary_id = tx.get("beneficiary_id")
            if not customer_id:
                continue

            cust = self._node(self.CUSTOMER, customer_id)
            g.add_node(cust)

            if device_id:
                dev = self._node(self.DEVICE, device_id)
                g.add_node(dev)
                g.add_edge(cust, dev, kind="uses_device")
                device_to_customers[device_id].add(customer_id)

            if beneficiary_id:
                ben = self._node(self.BENEFICIARY, beneficiary_id)
                g.add_node(ben)
                g.add_edge(cust, ben, kind="pays_beneficiary")
                beneficiary_to_customers[beneficiary_id].add(customer_id)

        # Link customers sharing a device or beneficiary (cross-account edges)
        for device_id, customers in device_to_customers.items():
            cust_nodes = [self._node(self.CUSTOMER, c) for c in customers]
            for i in range(len(cust_nodes)):
                for j in range(i + 1, len(cust_nodes)):
                    g.add_edge(cust_nodes[i], cust_nodes[j], kind="shared_device", device_id=device_id)

        for beneficiary_id, customers in beneficiary_to_customers.items():
            cust_nodes = [self._node(self.CUSTOMER, c) for c in customers]
            for i in range(len(cust_nodes)):
                for j in range(i + 1, len(cust_nodes)):
                    g.add_edge(cust_nodes[i], cust_nodes[j], kind="shared_beneficiary", beneficiary_id=beneficiary_id)

        self._graph = g
        return g

    def cluster_size(self, entity_type: str, entity_id: str) -> int:
        if not entity_id:
            return 1
        g = self.build()
        node = self._node(entity_type, entity_id)
        if node not in g:
            return 1
        return len(nx.node_connected_component(g, node))

    def find_cross_account_clusters(self, min_customers: int = 2) -> List[Dict[str, Any]]:
        """Return connected components with multiple customers (composite / mule rings)."""
        g = self.build()
        clusters: List[Dict[str, Any]] = []
        seen: Set[frozenset] = set()

        for component in nx.connected_components(g):
            customers = sorted(
                n.split(":", 1)[1]
                for n in component
                if self._node_types.get(n) == self.CUSTOMER
            )
            if len(customers) < min_customers:
                continue
            key = frozenset(customers)
            if key in seen:
                continue
            seen.add(key)

            devices = sorted(
                n.split(":", 1)[1]
                for n in component
                if self._node_types.get(n) == self.DEVICE
            )
            beneficiaries = sorted(
                n.split(":", 1)[1]
                for n in component
                if self._node_types.get(n) == self.BENEFICIARY
            )
            shared_device_links = sum(
                1 for _, _, d in g.subgraph(component).edges(data=True) if d.get("kind") == "shared_device"
            )
            shared_ben_links = sum(
                1 for _, _, d in g.subgraph(component).edges(data=True) if d.get("kind") == "shared_beneficiary"
            )

            clusters.append({
                "customer_ids": customers,
                "customer_count": len(customers),
                "device_count": len(devices),
                "beneficiary_count": len(beneficiaries),
                "shared_device_edges": shared_device_links,
                "shared_beneficiary_edges": shared_ben_links,
                "cluster_size": len(component),
            })

        return sorted(clusters, key=lambda c: (-c["customer_count"], -c["cluster_size"]))

    def stats(self) -> Dict[str, Any]:
        g = self.build()
        customers = [n for n, t in self._node_types.items() if t == self.CUSTOMER]
        return {
            "nodes": g.number_of_nodes(),
            "edges": g.number_of_edges(),
            "customers": len(customers),
            "components": nx.number_connected_components(g),
            "cross_account_clusters": len(self.find_cross_account_clusters()),
        }
