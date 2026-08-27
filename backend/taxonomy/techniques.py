"""
Attack technique taxonomy — the granular layer Blue needs and Red executes.

Two levels (see docs/SANDBOX_CONTRACT.md):

  surface     (7)   which control chain adjudicates. One orchestrator handler each.
  technique  (~35)  what the attacker actually did. Red's routing key, Blue's
                    label and report dimension.

Every technique is **derived from KB axes**, not invented:

  family_id            57 canonical families (data/knowledge/canonical/attacks)
  rail                 upi | card | bank_transfer | crypto | wallet
  channel              mobile_app | web | api | agent | voice | email | sms | video
  mutation_dimension   amount, timing, velocity, threshold_hug, agent_goal, ...

So `initiate_crypto_conversion` is the payment surface with `rail=crypto`;
`execute_vishing_call` is the auth_se surface with `channel=voice`;
`poison_agent_memory` is family AG-003. The technique carries no control logic of
its own — controls come from its family's `targeted_control_ids`, evaluated by the
KB rule engine. That is what keeps 21 distinct control verdicts achievable with
7 handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Adjudicated control surfaces. Each has exactly one orchestrator handler.
SURFACES = (
    "payment",       # 15-engine payment chain
    "agent",         # AI agent / agentic commerce context
    "auth_se",       # authentication + social engineering
    "kyc",           # identity evidence (documents, biometrics, liveness)
    "open_banking",  # third-party consent / TPP
    "device",        # device + session integrity
    "network",       # cross-account orchestration
)

# Surface-level entry action, used when Red has no specific technique in mind.
SURFACE_ENTRY_ACTION: Dict[str, str] = {
    "payment": "initiate_payment",
    "agent": "simulate_genai_context",
    "auth_se": "simulate_social_engineering",
    "kyc": "submit_kyc_evidence",
    "open_banking": "request_consent",
    "device": "establish_session",
    "network": "orchestrate_network",
}


@dataclass(frozen=True)
class Technique:
    """One concrete attacker action, resolved to a surface and a KB family."""

    action_type: str
    surface: str
    family_id: Optional[str] = None
    rail: Optional[str] = None
    channel: Optional[str] = None
    mutation: Optional[str] = None
    description: str = ""
    # Payload defaults merged into the action payload by the Red Team planner.
    payload_defaults: Dict[str, Any] = field(default_factory=dict)

    @property
    def entry_action(self) -> str:
        return SURFACE_ENTRY_ACTION[self.surface]


def _t(*args, **kwargs) -> Technique:
    return Technique(*args, **kwargs)


_TECHNIQUE_LIST: List[Technique] = [
    # ---------------------------------------------------------------- payment
    _t("initiate_upi_payment", "payment", rail="upi",
       description="Standard UPI push payment"),
    _t("initiate_card_payment", "payment", rail="card",
       description="Card-not-present authorization",
       payload_defaults={"card_present": 0}),
    _t("initiate_bank_transfer", "payment", rail="bank_transfer",
       description="Account-to-account transfer"),
    _t("initiate_crypto_conversion", "payment", rail="crypto",
       description="Fiat-to-crypto conversion for off-ramp"),
    _t("initiate_wallet_transfer", "payment", rail="wallet",
       description="Wallet-to-wallet value movement"),
    _t("initiate_threshold_optimized_payment", "payment", rail="upi",
       mutation="threshold_hug",
       description="Amount tuned just under a reporting/limit threshold",
       payload_defaults={"threshold_hug": True}),
    _t("initiate_micro_payment_burst", "payment", rail="upi", mutation="velocity",
       description="High-frequency low-value burst to stay under per-tx limits",
       payload_defaults={"burst": True}),
    _t("initiate_mule_pass_through", "payment", rail="bank_transfer",
       mutation="beneficiary_novelty",
       description="Rapid in-out movement through a mule account",
       payload_defaults={"is_new_beneficiary": 1}),
    _t("evade_acquirer_monitoring", "payment", family_id="ACQ-002", rail="card",
       description="GenAI-tuned pattern shaping to stay under acquirer thresholds"),

    # ------------------------------------------------------------------ agent
    _t("inject_prompt_agent", "agent", family_id="AG-001", channel="agent",
       description="Indirect prompt injection hijacking agent instructions"),
    _t("impersonate_agent", "agent", family_id="AG-002", channel="agent",
       description="Malicious agent posing as a trusted counterparty agent"),
    _t("poison_agent_memory", "agent", family_id="AG-003", channel="agent",
       description="Persistent context/memory poisoning across sessions"),
    _t("inject_a2a_communication", "agent", family_id="AG-004", channel="api",
       description="Agent-to-agent channel manipulation"),
    _t("adapt_autonomous_fraud", "agent", family_id="AG-005", channel="agent",
       description="Autonomous adaptive agent probing for a working path"),
    _t("exploit_agent_payment_protocol", "agent", family_id="GP-004", channel="api",
       description="Agentic payment protocol / mandate abuse"),

    # ---------------------------------------------------------------- auth_se
    _t("send_phishing_email", "auth_se", family_id="AUTH-001", channel="email",
       description="GenAI-personalised credential phishing"),
    _t("send_smishing_message", "auth_se", family_id="AUTH-001", channel="sms",
       description="SMS-delivered credential phishing"),
    _t("send_bec_email", "auth_se", family_id="AUTH-001", channel="email",
       description="Business email compromise / invoice redirection"),
    _t("execute_otp_social_engineering", "auth_se", family_id="AUTH-002",
       channel="voice",
       description="Coercing the victim into disclosing a one-time passcode"),
    _t("execute_vishing_call", "auth_se", family_id="AUTH-002", channel="voice",
       description="Voice-cloned call impersonating the bank"),
    _t("exploit_auth_recovery", "auth_se", family_id="AUTH-003", channel="web",
       description="Authentication recovery / reset flow exploitation"),

    # -------------------------------------------------------------------- kyc
    _t("submit_deepfake_biometric", "kyc", family_id="SEP-001", channel="video",
       description="Synthetic face/liveness bypass at video KYC"),
    _t("submit_document_forgery", "kyc", family_id="SEP-001", channel="web",
       description="GenAI-forged identity document"),
    _t("submit_recovery_document_fraud", "kyc", family_id="ATO-001", channel="web",
       description="Forged documents driving an account-recovery takeover"),
    _t("submit_synthetic_identity_onboarding", "kyc", family_id="ATO-002",
       channel="web",
       description="Fully synthetic identity onboarded as a new customer"),

    # ----------------------------------------------------------- open_banking
    _t("request_broad_consent", "open_banking", family_id="OB-001", channel="web",
       description="Over-broad data/payment consent scope"),
    _t("abuse_consent_scope_creep", "open_banking", family_id="OB-001", channel="api",
       description="Incremental scope escalation after initial consent"),
    _t("replay_stolen_consent_token", "open_banking", family_id="OB-001", channel="api",
       description="Reuse of an exfiltrated consent token"),
    _t("register_malicious_tpp", "open_banking", family_id="OB-002", channel="web",
       description="Fake third-party provider registration"),

    # ----------------------------------------------------------------- device
    _t("deploy_remote_access_trojan", "device", family_id="RAT-001",
       channel="mobile_app",
       description="On-device remote access / overlay control"),
    _t("execute_automated_bot_interaction", "device", family_id="BOT-001",
       channel="api",
       description="Agent-driven automated interaction at machine speed"),
    _t("evade_behavioral_biometrics", "device", family_id="BBE-001",
       channel="mobile_app",
       description="GAN-generated human-like interaction telemetry"),

    # ---------------------------------------------------------------- network
    _t("orchestrate_fraud_ring", "network", family_id="N-002",
       description="AI-coordinated multi-account fraud ring"),
    _t("coordinate_multi_stage_campaign", "network", family_id="N-003",
       description="Multi-stage campaign coordinated across lifecycle stages"),
    _t("socially_engineer_aml_investigator", "network", family_id="AML-005",
       description="GenAI narrative targeting the AML review process"),
]

TECHNIQUES: Dict[str, Technique] = {t.action_type: t for t in _TECHNIQUE_LIST}


def resolve_technique(action_type: str) -> Optional[Technique]:
    """Look up a technique by its action_type."""
    return TECHNIQUES.get(action_type)


def surface_for_action(action_type: str) -> Optional[str]:
    """
    Surface that adjudicates an action.

    Accepts both technique names (`poison_agent_memory`) and surface entry
    actions (`simulate_genai_context`).
    """
    technique = TECHNIQUES.get(action_type)
    if technique:
        return technique.surface
    for surface, entry in SURFACE_ENTRY_ACTION.items():
        if entry == action_type:
            return surface
    return None


def techniques_for_surface(surface: str) -> List[Technique]:
    return [t for t in _TECHNIQUE_LIST if t.surface == surface]


def techniques_for_family(family_id: str) -> List[Technique]:
    """Techniques that instantiate a KB family. Empty for unmapped families."""
    return [t for t in _TECHNIQUE_LIST if t.family_id == family_id]


def all_action_types() -> frozenset:
    """Every action the sandbox can adjudicate: techniques + surface entries."""
    return frozenset(TECHNIQUES) | frozenset(SURFACE_ENTRY_ACTION.values())
