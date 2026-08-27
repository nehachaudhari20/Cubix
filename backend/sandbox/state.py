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
        recent = [
            t for t in self.transactions
            if (ts := t.get("timestamp")) is not None and ts > cutoff
        ]
        if not recent:
            return 0.0
        return sum(t.get("amount", 0) for t in recent) / len(recent)
    
    def get_tx_count_24h(self) -> int:
        cutoff = datetime.now() - timedelta(hours=24)
        return len([
            t for t in self.transactions
            if (ts := t.get("timestamp")) is not None and ts > cutoff
        ])

    def get_tx_count_1h(self) -> int:
        cutoff = datetime.now() - timedelta(hours=1)
        return len([
            t for t in self.transactions
            if (ts := t.get("timestamp")) is not None and ts > cutoff
        ])

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


@dataclass
class SyntheticMerchant:
    """A synthetic merchant in the sandbox."""
    merchant_id: str
    name: str
    mcc: str
    declared_mcc: str
    risk_score: float
    kyb_verified: bool
    created_at: datetime
    owner_customer_id: Optional[str] = None
    is_active: bool = True


@dataclass
class SyntheticBeneficiary:
    """A payee linked to a customer."""
    beneficiary_id: str
    customer_id: str
    name: str
    account_ref: str
    created_at: datetime
    is_verified: bool = True
    risk_score: float = 0.2

    @property
    def is_new(self) -> bool:
        return (datetime.now() - self.created_at).days < 7


@dataclass
class SyntheticAgent:
    """An AI agent acting on a customer's behalf (agentic commerce)."""
    agent_id: str
    customer_id: str
    created_at: datetime
    mandate_scope: List[str] = field(default_factory=list)
    tool_scope: List[str] = field(default_factory=list)
    spend_limit: float = 25000.0
    # Memory integrity degrades as poisoning attempts land — persists across turns
    memory_integrity: float = 1.0
    instruction_fidelity: float = 1.0
    is_verified: bool = True
    session_count: int = 0
    poisoning_attempts: int = 0

    def get_age_days(self) -> int:
        return (datetime.now() - self.created_at).days


@dataclass
class SyntheticConsent:
    """A third-party (TPP) data/payment consent grant."""
    consent_id: str
    customer_id: str
    tpp_id: str
    scopes: List[str]
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool = True
    token_ref: Optional[str] = None
    use_count: int = 0
    scope_escalations: int = 0

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and datetime.now() > self.expires_at


@dataclass
class SyntheticTPP:
    """A third-party provider registered against the open-banking surface."""
    tpp_id: str
    name: str
    created_at: datetime
    is_licensed: bool = True
    registration_age_days: int = 0
    risk_score: float = 0.2


@dataclass
class SyntheticKYCSubmission:
    """One identity-evidence submission (document, biometric, liveness)."""
    submission_id: str
    customer_id: str
    evidence_type: str  # document | biometric | liveness | video_kyc
    created_at: datetime
    accepted: bool = False
    liveness_passed: bool = True
    document_verified: bool = True
    reason: str = ""


@dataclass
class AuthEvent:
    """One authentication / social-engineering interaction."""
    event_id: str
    customer_id: str
    channel: str
    method: str
    created_at: datetime
    succeeded: bool = False
    otp_disclosed: bool = False
    victim_coerced: bool = False


class SandboxState:
    """Manages all state in the payment sandbox."""

    def __init__(self):
        self.customers: Dict[str, SyntheticCustomer] = {}
        self.devices: Dict[str, SyntheticDevice] = {}
        self.accounts: Dict[str, SyntheticAccount] = {}
        self.merchants: Dict[str, SyntheticMerchant] = {}
        self.beneficiaries: Dict[str, SyntheticBeneficiary] = {}
        self.transaction_log: List[Dict] = []

        # Non-payment surface state — carries forward between actions and rounds,
        # so the same customer/agent is never a blank slate on the next attempt.
        self.agents: Dict[str, SyntheticAgent] = {}
        self.consents: Dict[str, SyntheticConsent] = {}
        self.tpps: Dict[str, SyntheticTPP] = {}
        self.kyc_submissions: Dict[str, SyntheticKYCSubmission] = {}
        self.auth_events: List[AuthEvent] = []
        self.surface_log: List[Dict] = []

    def get_customer(self, customer_id: str) -> Optional[SyntheticCustomer]:
        return self.customers.get(customer_id)
    
    def get_device(self, device_id: str) -> Optional[SyntheticDevice]:
        return self.devices.get(device_id)
    
    def get_account(self, account_id: str) -> Optional[SyntheticAccount]:
        return self.accounts.get(account_id)

    def get_merchant(self, merchant_id: str) -> Optional[SyntheticMerchant]:
        return self.merchants.get(merchant_id)

    def get_beneficiary(self, beneficiary_id: str) -> Optional[SyntheticBeneficiary]:
        return self.beneficiaries.get(beneficiary_id)
    
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
        if transaction.get("timestamp") is None:
            transaction = {**transaction, "timestamp": datetime.now()}
        self.transaction_log.append(transaction)
        customer_id = transaction.get("customer_id")
        if customer_id and customer_id in self.customers:
            self.customers[customer_id].transactions.append(transaction)

    # ------------------------------------------------------------------
    # Non-payment surface accessors
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> Optional[SyntheticAgent]:
        return self.agents.get(agent_id)

    def get_consent(self, consent_id: str) -> Optional[SyntheticConsent]:
        return self.consents.get(consent_id)

    def get_tpp(self, tpp_id: str) -> Optional[SyntheticTPP]:
        return self.tpps.get(tpp_id)

    def get_or_create_agent(self, agent_id: str, customer_id: str, **kwargs) -> SyntheticAgent:
        """Agents persist: repeated attacks accumulate against the same agent."""
        agent = self.agents.get(agent_id)
        if agent is None:
            agent = SyntheticAgent(
                agent_id=agent_id,
                customer_id=customer_id,
                created_at=datetime.now(),
                **kwargs,
            )
            self.agents[agent_id] = agent
        agent.session_count += 1
        return agent

    def add_auth_event(self, event: AuthEvent) -> AuthEvent:
        self.auth_events.append(event)
        return event

    def get_auth_events(self, customer_id: str, hours: int = 24) -> List[AuthEvent]:
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            e for e in self.auth_events
            if e.customer_id == customer_id and e.created_at > cutoff
        ]

    def get_kyc_submissions(self, customer_id: str) -> List[SyntheticKYCSubmission]:
        return [s for s in self.kyc_submissions.values() if s.customer_id == customer_id]

    def get_customer_consents(self, customer_id: str) -> List[SyntheticConsent]:
        return [c for c in self.consents.values() if c.customer_id == customer_id]

    def record_surface_event(self, event: Dict[str, Any]) -> None:
        """Append an adjudicated non-payment action to the surface history."""
        if event.get("timestamp") is None:
            event = {**event, "timestamp": datetime.now()}
        self.surface_log.append(event)

    def count_surface_events(
        self,
        customer_id: str,
        surface: Optional[str] = None,
        hours: int = 24,
    ) -> int:
        cutoff = datetime.now() - timedelta(hours=hours)
        return len([
            e for e in self.surface_log
            if e.get("customer_id") == customer_id
            and (surface is None or e.get("surface") == surface)
            and (ts := e.get("timestamp")) is not None and ts > cutoff
        ])

    def count_distinct_payers_to_beneficiary(self, beneficiary_id: str) -> int:
        """Count distinct customers who paid a given beneficiary."""
        payers = set()
        for tx in self.transaction_log:
            if tx.get("beneficiary_id") == beneficiary_id and tx.get("customer_id"):
                payers.add(tx["customer_id"])
        return len(payers)