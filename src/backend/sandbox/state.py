"""
Sandbox State Management
Maintains synthetic payment ecosystem state in memory.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

@dataclass
class SyntheticCustomer:
    """A synthetic customer in the sandbox."""
    customer_id: str
    name: str
    pan: str
    dob: str
    address: str
    created_at: datetime
    verified: bool = True
    trust_score: float = 0.5
    account_age_days: int = 0
    transactions: List[Dict] = field(default_factory=list)
    
    def get_avg_amount_7d(self) -> float:
        cutoff = datetime.now() - timedelta(days=7)
        recent = [t for t in self.transactions if t.get("timestamp") > cutoff]
        if not recent:
            return 0.0
        return sum(t.get("amount", 0) for t in recent) / len(recent)
    
    def get_tx_count_24h(self) -> int:
        cutoff = datetime.now() - timedelta(hours=24)
        return len([t for t in self.transactions if t.get("timestamp") > cutoff])

@dataclass
class SyntheticDevice:
    """A synthetic device in the sandbox."""
    device_id: str
    customer_id: str
    fingerprint: Dict[str, Any]
    first_seen: datetime
    last_seen: datetime
    is_known: bool = True
    
    def get_age_days(self) -> int:
        return (datetime.now() - self.first_seen).days

@dataclass
class SyntheticAccount:
    """A synthetic account (bank account, wallet, etc.)."""
    account_id: str
    customer_id: str
    balance: float
    created_at: datetime
    is_active: bool = True
    daily_limit: float = 100000.0
    monthly_limit: float = 1000000.0

class SandboxState:
    """Manages all state in the payment sandbox."""
    
    def __init__(self):
        self.customers: Dict[str, SyntheticCustomer] = {}
        self.devices: Dict[str, SyntheticDevice] = {}
        self.accounts: Dict[str, SyntheticAccount] = {}
        self.transaction_log: List[Dict] = []
        
    def get_customer(self, customer_id: str) -> Optional[SyntheticCustomer]:
        return self.customers.get(customer_id)
    
    def get_device(self, device_id: str) -> Optional[SyntheticDevice]:
        return self.devices.get(device_id)
    
    def get_account(self, account_id: str) -> Optional[SyntheticAccount]:
        return self.accounts.get(account_id)
    
    def register_device(self, customer_id: str, fingerprint: Dict) -> SyntheticDevice:
        device_id = f"dev_{uuid.uuid4().hex[:8]}"
        device = SyntheticDevice(
            device_id=device_id,
            customer_id=customer_id,
            fingerprint=fingerprint,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            is_known=True
        )
        self.devices[device_id] = device
        return device
    
    def add_transaction(self, transaction: Dict):
        """Add a transaction to the log and update customer history."""
        self.transaction_log.append(transaction)
        customer_id = transaction.get("customer_id")
        if customer_id and customer_id in self.customers:
            self.customers[customer_id].transactions.append(transaction)