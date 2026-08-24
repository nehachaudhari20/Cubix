#!/usr/bin/env python3
"""Build the complete canonical knowledge model from existing registries.

Does not invent attack families. Does not write concrete instance amounts or
timestamps onto vectors. Does not modify legacy runtime KB files.

Writes only the nested layout:
  data/knowledge/canonical/{attacks,defense,lifecycle,simulation,genai,evidence}/
Does not write duplicate flat copies.
"""
from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "data" / "knowledge"
CANONICAL = LEGACY / "canonical"
DATASET_PY = ROOT / "src" / "scripts" / "generate_dataset.py"
FEATURES_JSON = ROOT / "data" / "models" / "features.json"

DATASET_ONLY_FAMILY_IDS = {
    "MCH-001", "MCH-002", "MCH-003", "MCH-004", "MCH-005", "MCH-006",
    "PI-F001", "PI-F002", "PI-F003", "PI-F004",
}

PATTERN_KEYWORDS = {
    "mule": ["mule", "cash-out", "cash out", "beneficiary", "layering", "recruitment"],
    "merchant": ["merchant", "mcc", "acquirer", "acq-", "kyb", "misrepresentation"],
    "identity": ["synthetic identity", "sif-", "identity fabrication", "document fabrication", "kyc"],
    "aml": ["aml", "structuring", "smurfing", "money laundering", "layering"],
    "velocity": ["velocity", "threshold", "low-and-slow", "authorization feature", "splitting"],
    "account": ["account creation", "onboarding", "open account", "account farming"],
    "auth": ["authentication", "account takeover", "ato-", "credential"],
}

TEMPLATE_SPECS = {
    "mule": {
        "template_id": "TPL-MULE",
        "name": "New-beneficiary cash-out / mule journey",
        "required_entities": ["customer", "device", "beneficiary", "payment"],
        "supported_action_types": ["register_customer", "register_device", "link_beneficiary", "initiate_payment"],
        "required_state_keys": ["customer_id", "device_id", "beneficiary_id"],
        "parameter_ids": ["PAR-AMOUNT", "PAR-BENEFICIARY-NOVELTY", "PAR-VELOCITY", "PAR-DEVICE-AGE", "PAR-TIMING"],
    },
    "merchant": {
        "template_id": "TPL-MERCHANT",
        "name": "Merchant onboarding + MCC misrepresentation journey",
        "required_entities": ["customer", "device", "merchant", "payment"],
        "supported_action_types": ["register_customer", "register_device", "onboard_merchant", "initiate_payment"],
        "required_state_keys": ["customer_id", "device_id", "merchant_id"],
        "parameter_ids": ["PAR-AMOUNT", "PAR-MERCHANT-FAMILIARITY", "PAR-MCC", "PAR-TIMING"],
    },
    "identity": {
        "template_id": "TPL-IDENTITY",
        "name": "Synthetic / low-trust identity provisioning journey",
        "required_entities": ["customer", "device", "account", "payment"],
        "supported_action_types": ["register_customer", "register_device", "open_account", "initiate_payment"],
        "required_state_keys": ["customer_id", "device_id", "trust_score"],
        "parameter_ids": ["PAR-TRUST-SCORE", "PAR-ACCOUNT-AGE", "PAR-AMOUNT", "PAR-DEVICE-AGE"],
    },
    "aml": {
        "template_id": "TPL-AML",
        "name": "Structuring / threshold-hugging payment sequence",
        "required_entities": ["customer", "device", "account", "payment"],
        "supported_action_types": ["register_customer", "register_device", "open_account", "initiate_payment"],
        "required_state_keys": ["customer_id", "device_id", "account_id"],
        "parameter_ids": ["PAR-AMOUNT", "PAR-VELOCITY", "PAR-SEQUENCE-GAP", "PAR-TIMING"],
    },
    "velocity": {
        "template_id": "TPL-VELOCITY",
        "name": "Burst / low-and-slow velocity evasion sequence",
        "required_entities": ["customer", "device", "payment"],
        "supported_action_types": ["register_customer", "register_device", "initiate_payment"],
        "required_state_keys": ["customer_id", "device_id"],
        "parameter_ids": ["PAR-AMOUNT", "PAR-VELOCITY", "PAR-SEQUENCE-GAP", "PAR-RETRY-COUNT"],
    },
    "account": {
        "template_id": "TPL-ACCOUNT",
        "name": "Account opening then first-payment journey",
        "required_entities": ["customer", "device", "account", "payment"],
        "supported_action_types": ["register_customer", "register_device", "open_account", "initiate_payment"],
        "required_state_keys": ["customer_id", "account_id"],
        "parameter_ids": ["PAR-ACCOUNT-AGE", "PAR-AMOUNT", "PAR-TRUST-SCORE"],
    },
    "auth": {
        "template_id": "TPL-AUTH",
        "name": "Authentication / ATO then payment journey",
        "required_entities": ["customer", "device", "payment"],
        "supported_action_types": ["register_customer", "register_device", "authenticate", "initiate_payment"],
        "required_state_keys": ["customer_id", "device_id"],
        "parameter_ids": ["PAR-DEVICE-AGE", "PAR-AMOUNT", "PAR-SESSION-DURATION", "PAR-TIMING"],
    },
    "payment_probe": {
        "template_id": "TPL-PAYMENT-PROBE",
        "name": "Generic payment-probe journey",
        "required_entities": ["customer", "device", "payment"],
        "supported_action_types": ["register_customer", "register_device", "initiate_payment"],
        "required_state_keys": ["customer_id", "device_id"],
        "parameter_ids": ["PAR-AMOUNT", "PAR-RAIL", "PAR-TIMING"],
    },
    "agentic": {
        "template_id": "TPL-AGENTIC-NONEXEC",
        "name": "Agentic specification (not currently sandbox-executable)",
        "required_entities": ["customer", "agent", "payment"],
        "supported_action_types": [],
        "required_state_keys": [],
        "parameter_ids": ["PAR-AMOUNT"],
    },
}

PARAMETERS = [
    {
        "parameter_id": "PAR-AMOUNT",
        "name": "amount",
        "value_type": "number",
        "unit": "INR",
        "description": "Payment amount. Sample from the customer baseline, then apply an attacker mutation. Never store a concrete rupee value on a vector.",
        "legitimate_source": "data/baseline/baseline_transactions.csv amount distribution, conditioned on customer/rail",
        "mutation_strategies": ["threshold_hug", "gradual_escalation", "burst_spike", "baseline_preserve"],
        "attacker_controllable": True,
        "constraints": {"must_condition_on": ["customer_baseline", "rail"]},
        "related_feature_ids": ["amount", "amount_to_avg_7d_ratio", "amount_zscore_account", "avg_amount_last_7d"],
        "sandbox_config_ref": "EXECUTABLE_DEFAULTS.payment_initiation.amount_limit_*",
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-TIMING",
        "name": "transaction_time",
        "value_type": "duration",
        "unit": None,
        "description": "Hour/day placement relative to the customer's legitimate activity, not a free random timestamp.",
        "legitimate_source": "baseline hour_of_day / day_of_week / is_night",
        "mutation_strategies": ["night_shift", "preserve_customer_hours", "off_cycle"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["hour_of_day", "day_of_week", "is_night"],
        "sandbox_config_ref": None,
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-DEVICE-AGE",
        "name": "device_age",
        "value_type": "integer",
        "unit": "days",
        "description": "Age of the device used for the action. New-device attacks mutate this; legitimate counterparts keep a known device.",
        "legitimate_source": "sandbox device.first_seen / baseline device_age_days",
        "mutation_strategies": ["new_device", "seasoned_device", "device_switch"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["device_age_days", "is_new_device", "distinct_devices_last_7d"],
        "sandbox_config_ref": "EXECUTABLE_DEFAULTS.device_session",
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-BENEFICIARY-NOVELTY",
        "name": "beneficiary_novelty",
        "value_type": "boolean",
        "unit": None,
        "description": "Whether the payee is new to the customer. Attacker-controllable via link_beneficiary; legitimate counterparts use known family/rent payees.",
        "legitimate_source": "sandbox beneficiary.created_at / baseline is_new_beneficiary",
        "mutation_strategies": ["new_beneficiary", "known_beneficiary", "mule_reuse"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["is_new_beneficiary", "distinct_beneficiaries_last_24h"],
        "sandbox_config_ref": "EXECUTABLE_DEFAULTS.mule_cashout",
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-VELOCITY",
        "name": "transaction_velocity",
        "value_type": "integer",
        "unit": "count",
        "description": "Number of payments in the attack sequence window. Mutation strategies change spacing, not independent randomization of every field.",
        "legitimate_source": "baseline transaction_count_last_1h / last_24h",
        "mutation_strategies": ["burst", "low_and_slow", "just_under_limit"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["velocity_score", "transaction_count_last_1h", "transaction_count_last_24h"],
        "sandbox_config_ref": "EXECUTABLE_DEFAULTS.payment_initiation.velocity_*",
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-SEQUENCE-GAP",
        "name": "sequence_gap",
        "value_type": "integer",
        "unit": "seconds",
        "description": "Gap between successive actions in a multi-step vector.",
        "legitimate_source": "baseline seconds_since_prev_tx",
        "mutation_strategies": ["compress", "stretch", "preserve"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["seconds_since_prev_tx", "campaign_step"],
        "sandbox_config_ref": None,
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-ACCOUNT-AGE",
        "name": "account_age",
        "value_type": "integer",
        "unit": "days",
        "description": "Tenure of the paying account.",
        "legitimate_source": "sandbox customer.created_at / baseline account_age_days",
        "mutation_strategies": ["fresh_account", "seasoned_account"],
        "attacker_controllable": False,
        "constraints": {"typically_prerequisite": True},
        "related_feature_ids": ["account_age_days", "account_tx_count_to_date"],
        "sandbox_config_ref": "EXECUTABLE_DEFAULTS.identity_kyc.young_account_days",
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-MERCHANT-FAMILIARITY",
        "name": "merchant_familiarity",
        "value_type": "number",
        "unit": None,
        "description": "How often this customer has paid this merchant.",
        "legitimate_source": "baseline merchant_familiarity_score",
        "mutation_strategies": ["novel_merchant", "known_merchant"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["merchant_familiarity_score", "merchant_risk_score", "merchant_category_code"],
        "sandbox_config_ref": "EXECUTABLE_DEFAULTS.merchant",
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-MCC",
        "name": "merchant_category_code",
        "value_type": "enum",
        "unit": None,
        "description": "Declared vs actual MCC. Vector stores the *dimension*, not a concrete MCC like 7995 as if it were an instance.",
        "legitimate_source": "baseline merchant_category_code",
        "mutation_strategies": ["declare_grocery_actual_gambling", "preserve_declared"],
        "attacker_controllable": True,
        "constraints": {"do_not_treat_as_production_mcc_policy": True},
        "related_feature_ids": ["merchant_category_code"],
        "sandbox_config_ref": None,
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-RAIL",
        "name": "payment_rail",
        "value_type": "enum",
        "unit": None,
        "description": "Allowed rails for instantiation. Sample from the family-allowed set; do not invent a rail the family cannot use.",
        "legitimate_source": "baseline payment_rail",
        "mutation_strategies": ["keep_customer_rail", "cross_rail"],
        "attacker_controllable": True,
        "constraints": {"allowed_values_ref": "vector.rails"},
        "related_feature_ids": ["payment_rail"],
        "sandbox_config_ref": None,
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-TRUST-SCORE",
        "name": "trust_score",
        "value_type": "number",
        "unit": None,
        "description": "Synthetic KYC/trust prior used by identity journeys. Sandbox-local, not a production Mastercard score.",
        "legitimate_source": "sandbox customer.trust_score",
        "mutation_strategies": ["low_trust", "high_trust_camouflage"],
        "attacker_controllable": False,
        "constraints": {"range": [0, 1]},
        "related_feature_ids": ["account_age_days"],
        "sandbox_config_ref": "EXECUTABLE_DEFAULTS.identity_kyc.low_trust_threshold",
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-SESSION-DURATION",
        "name": "session_duration",
        "value_type": "integer",
        "unit": "seconds",
        "description": "Session length before payment. Used by ATO/device vectors.",
        "legitimate_source": None,
        "mutation_strategies": ["short_session", "normal_session"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["seconds_since_prev_tx"],
        "sandbox_config_ref": None,
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-RETRY-COUNT",
        "name": "retry_count",
        "value_type": "integer",
        "unit": "count",
        "description": "Authorization retries or repeated probes in a velocity vector.",
        "legitimate_source": None,
        "mutation_strategies": ["single_shot", "retry_burst"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["transaction_count_last_1h", "velocity_score"],
        "sandbox_config_ref": None,
        "origin": "implementation_derived",
    },
    {
        "parameter_id": "PAR-GEO-DISTANCE",
        "name": "geo_distance",
        "value_type": "string",
        "unit": None,
        "description": "Location region relative to the customer baseline. Feature exists in training; sandbox fill is currently limited.",
        "legitimate_source": "baseline location_region / location_country",
        "mutation_strategies": ["preserve_region", "distant_region"],
        "attacker_controllable": True,
        "constraints": {},
        "related_feature_ids": ["location_region", "location_country"],
        "sandbox_config_ref": None,
        "origin": "implementation_derived",
    },
]

CAPABILITIES = [
    {"capability_id": "CAP-0001", "name": "synthetic_content_generation", "role": "amplification",
     "description": "Generate realistic text, images, or documents at scale.",
     "examples": ["synthetic narratives", "fake websites", "generated invoices"]},
    {"capability_id": "CAP-0002", "name": "personalization", "role": "amplification",
     "description": "Adapt lures or payloads to a specific victim or institution.",
     "examples": ["spear phishing", "hyper-personalized correspondence"]},
    {"capability_id": "CAP-0003", "name": "scale_automation", "role": "amplification",
     "description": "Run many parallel identities, accounts, or probes.",
     "examples": ["account farming", "bulk creation", "distributed testing"]},
    {"capability_id": "CAP-0004", "name": "adaptive_evasion", "role": "amplification",
     "description": "Change patterns in response to controls or model scores.",
     "examples": ["threshold hugging", "behavioral camouflage", "strategy adaptation"]},
    {"capability_id": "CAP-0005", "name": "deepfake_identity", "role": "load_bearing",
     "description": "Synthesize a biometric or visual identity that is not a real person.",
     "examples": ["face swap", "synthetic biometrics", "deepfake video KYC"]},
    {"capability_id": "CAP-0006", "name": "voice_cloning", "role": "load_bearing",
     "description": "Clone or synthesize a voice for vishing or recovery.",
     "examples": ["vishing", "voice-based recovery"]},
    {"capability_id": "CAP-0007", "name": "document_forgery", "role": "load_bearing",
     "description": "Forge identity or supporting documents with generative models.",
     "examples": ["passport forgery", "utility bill forgery"]},
    {"capability_id": "CAP-0008", "name": "agentic_planning", "role": "load_bearing",
     "description": "An agent plans multi-step fraud without a human in the loop.",
     "examples": ["autonomous campaign planning", "self-evolving fraud"]},
    {"capability_id": "CAP-0009", "name": "agentic_tool_use", "role": "load_bearing",
     "description": "An agent uses payment/KYC/API tools to execute actions.",
     "examples": ["unauthorized tool calls", "agent shopping", "API manipulation"]},
    {"capability_id": "CAP-0010", "name": "prompt_injection", "role": "load_bearing",
     "description": "Hidden instructions steer an agent away from the user goal.",
     "examples": ["visual prompt injection", "goal hacking"]},
    {"capability_id": "CAP-0011", "name": "memory_poisoning", "role": "load_bearing",
     "description": "Corrupt agent memory or context so future actions are attacker-aligned.",
     "examples": ["sleeper memory", "cross-session injection"]},
    {"capability_id": "CAP-0012", "name": "social_engineering_generation", "role": "either",
     "description": "Generate social-engineering content (phishing, BEC, romance, digital arrest).",
     "examples": ["BEC", "romance scam", "digital arrest"]},
    {"capability_id": "CAP-0013", "name": "model_evasion", "role": "amplification",
     "description": "Probe or manipulate ML decision boundaries, labels, or training data.",
     "examples": ["boundary exploration", "label flipping", "AML model poisoning"]},
    {"capability_id": "CAP-0014", "name": "network_orchestration", "role": "either",
     "description": "Coordinate multiple identities, merchants, or mules as one operation.",
     "examples": ["fraud rings", "mule networks", "multi-account bust-out"]},
    {"capability_id": "CAP-0015", "name": "biometric_synthesis", "role": "load_bearing",
     "description": "Synthesize behavioral or physiological biometrics.",
     "examples": ["keystroke injection", "motion forecasting", "fingerprint/iris synthesis"]},
]

CAP_KEYWORDS = [
    (["prompt injection", "goal hacking", "visual prompt"], ["CAP-0010", "CAP-0009"]),
    (["memory poison", "context injection"], ["CAP-0011"]),
    (["agent imperson", "malicious agent", "agent-to-agent", "autonomous", "agentic", "ai agent"], ["CAP-0008", "CAP-0009"]),
    (["deepfake", "face swap", "synthetic biometric", "facial injection"], ["CAP-0005", "CAP-0015"]),
    (["voice clon", "vishing"], ["CAP-0006", "CAP-0012"]),
    (["document forg", "passport", "utility bill", "document fabrication"], ["CAP-0007"]),
    (["phish", "bec", "romance", "digital arrest", "social engineering", "impersonation"], ["CAP-0012", "CAP-0002"]),
    (["keystroke", "motion forecast", "behavioral biometric", "gan-based"], ["CAP-0015"]),
    (["model poison", "label flipping", "decision boundary", "adversarial", "feature manipulation", "fraud score"], ["CAP-0013"]),
    (["farming", "bulk", "mass ", "distributed", "portfolio", "ring", "network", "coordinated", "mesh"], ["CAP-0003", "CAP-0014"]),
    (["camouflage", "adaptive", "threshold", "evasion", "pattern-free", "low-and-slow"], ["CAP-0004"]),
    (["synthetic identity", "synthetic merchant", "ai-generated"], ["CAP-0001", "CAP-0003"]),
    (["mule", "layering", "cash-out"], ["CAP-0014"]),
]

FEATURE_KEYWORDS = [
    (["amount", "value", "threshold", "structuring", "smurf", "high-value", "large transfer", "currency"],
     ["amount", "amount_to_avg_7d_ratio", "amount_zscore_account", "avg_amount_last_7d"]),
    (["velocity", "burst", "frequency", "repeat", "rapid", "multiple transaction"],
     ["velocity_score", "transaction_count_last_1h", "transaction_count_last_24h"]),
    (["beneficiary", "payee", "mule", "redirect"],
     ["is_new_beneficiary", "distinct_beneficiaries_last_24h"]),
    (["device", "emulator", "fingerprint", "bot"],
     ["is_new_device", "device_age_days", "distinct_devices_last_7d"]),
    (["merchant", "mcc", "storefront", "acquirer"],
     ["merchant_category_code", "merchant_risk_score", "merchant_familiarity_score"]),
    (["account age", "new account", "tenure", "onboarding"],
     ["account_age_days", "account_tx_count_to_date"]),
    (["night", "hour", "timing", "temporal"],
     ["hour_of_day", "is_night", "day_of_week"]),
    (["auth", "otp", "biometric", "credential"],
     ["authentication_method", "auth_success"]),
    (["rail", "upi", "card", "wallet", "crypto"],
     ["payment_rail"]),
    (["card present", "card-not-present", "cnp"],
     ["card_present"]),
]

COUNTERPARTS = [
    {
        "counterpart_id": "LCP-0001",
        "name": "New phone + family beneficiary + rent at night",
        "description": "Looks like new-device + new-beneficiary + high-value night payment; is a customer replacing a phone and paying monthly rent to family.",
        "suspicious_pattern": "new device + new beneficiary + high-value + night",
        "legitimate_lookalike": "new phone + family beneficiary + monthly rent + night",
        "related_feature_names": ["is_new_device", "is_new_beneficiary", "amount", "is_night"],
        "origin": "implementation_derived",
    },
    {
        "counterpart_id": "LCP-0002",
        "name": "Salary split just under a round threshold",
        "description": "Several sub-threshold credits/debits that resemble structuring but are payroll or vendor splits.",
        "suspicious_pattern": "multiple just-under-threshold payments",
        "legitimate_lookalike": "salary disbursement or vendor invoice split",
        "related_feature_names": ["amount", "transaction_count_last_24h", "velocity_score"],
        "origin": "implementation_derived",
    },
    {
        "counterpart_id": "LCP-0003",
        "name": "First payment to a new school / hospital merchant",
        "description": "Novel merchant + uncommon MCC that is a real first-time education or medical payment.",
        "suspicious_pattern": "new merchant + unusual MCC + large first payment",
        "legitimate_lookalike": "first tuition or hospital bill at a genuine merchant",
        "related_feature_names": ["merchant_familiarity_score", "merchant_category_code", "amount"],
        "origin": "implementation_derived",
    },
    {
        "counterpart_id": "LCP-0004",
        "name": "Travel burst on a known device",
        "description": "Several payments in one hour that trip velocity rules during legitimate travel or festival shopping.",
        "suspicious_pattern": "high 1h velocity + elevated amount ratio",
        "legitimate_lookalike": "travel booking cluster or festival shopping on a known device",
        "related_feature_names": ["transaction_count_last_1h", "velocity_score", "is_new_device"],
        "origin": "implementation_derived",
    },
    {
        "counterpart_id": "LCP-0005",
        "name": "Young account used by a newly onboarded genuine customer",
        "description": "Low tenure + first payments that resemble synthetic bust-out but follow a real KYC pass.",
        "suspicious_pattern": "young account + immediate payment",
        "legitimate_lookalike": "newly verified customer making a first legitimate transfer",
        "related_feature_names": ["account_age_days", "account_tx_count_to_date", "amount"],
        "origin": "implementation_derived",
    },
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (value or "").casefold()).strip("_")
    return text or "variant"


def extract_dataset_config() -> dict[str, Any]:
    tree = ast.parse(DATASET_PY.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DOCUMENT_CONFIG":
                    return ast.literal_eval(node.value)
    raise RuntimeError("DOCUMENT_CONFIG not found")


def family_blob(family: dict[str, Any]) -> str:
    parts = [
        family.get("name") or "",
        family.get("attack_id") or "",
        family.get("simulation_type") or "",
        " ".join(family.get("variants") or []),
        " ".join(family.get("prerequisites") or []),
        " ".join(family.get("attack_flow") or []),
    ]
    return norm(" ".join(parts))


def classify_pattern(family: dict[str, Any]) -> str:
    blob = family_blob(family)
    scores = {key: 0 for key in PATTERN_KEYWORDS}
    for pattern, keywords in PATTERN_KEYWORDS.items():
        for keyword in keywords:
            if keyword in blob:
                scores[pattern] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "payment_probe"


def is_sandbox_executable(family: dict[str, Any]) -> bool:
    sim = norm(family.get("simulation_type") or "")
    if sim == "agentic":
        return False
    if "algorithmic" in sim or "hybrid" in sim:
        return True
    return classify_pattern(family) != "agentic"


def assign_capabilities(family: dict[str, Any]) -> list[str]:
    blob = family_blob(family)
    found: list[str] = []
    for keywords, caps in CAP_KEYWORDS:
        if any(keyword in blob for keyword in keywords):
            found.extend(caps)
    classification = family.get("genai_classification")
    if classification == "genai_load_bearing":
        if not found:
            found.extend(["CAP-0008", "CAP-0001"])
    elif classification == "genai_amplified":
        found.extend(["CAP-0001", "CAP-0004"])
    # unique, stable order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in found:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def allowed_rails(family: dict[str, Any], pattern: str) -> list[str]:
    blob = family_blob(family)
    rails = ["upi", "card", "bank_transfer"]
    if "crypto" in blob or "cash-out" in blob or family["attack_id"].startswith("CM-") or family["attack_id"].startswith("N-004"):
        rails.append("crypto")
    if "wallet" in blob:
        rails.append("wallet")
    if pattern == "auth":
        rails = ["card", "bank_transfer", "upi"]
    return rails


def allowed_channels(pattern: str, family: dict[str, Any]) -> list[str]:
    blob = family_blob(family)
    channels = ["mobile_app", "web"]
    if "agent" in blob or "api" in blob or family["attack_id"].startswith(("AG-", "GP-", "OB-")):
        channels.append("api")
        channels.append("agent")
    if pattern == "auth":
        channels.append("voice")
    return channels


def template_actions(pattern: str, executable: bool) -> list[dict[str, Any]]:
    if not executable:
        return [
            {
                "action_id": "step-01",
                "action_type": "specify_only",
                "parameters": {
                    "note": "Family is not sandbox-executable yet. Vector is a specification, not a concrete instance.",
                    "parameter_refs": ["PAR-AMOUNT"],
                },
            }
        ]
    setup = [
        {"action_id": "step-01", "action_type": "register_customer", "parameters": {"parameter_refs": ["PAR-TRUST-SCORE", "PAR-ACCOUNT-AGE"]}},
        {"action_id": "step-02", "action_type": "register_device", "parameters": {"parameter_refs": ["PAR-DEVICE-AGE"]}},
    ]
    extras: list[dict[str, Any]] = []
    n = 3
    if pattern in {"account", "aml", "identity"}:
        extras.append({"action_id": f"step-{n:02d}", "action_type": "open_account", "parameters": {"parameter_refs": ["PAR-ACCOUNT-AGE"]}})
        n += 1
    if pattern == "merchant":
        extras.append({"action_id": f"step-{n:02d}", "action_type": "onboard_merchant", "parameters": {"parameter_refs": ["PAR-MCC", "PAR-MERCHANT-FAMILIARITY"]}})
        n += 1
    if pattern == "mule":
        extras.append({"action_id": f"step-{n:02d}", "action_type": "link_beneficiary", "parameters": {"parameter_refs": ["PAR-BENEFICIARY-NOVELTY"]}})
        n += 1
    if pattern == "auth":
        extras.append({"action_id": f"step-{n:02d}", "action_type": "authenticate", "parameters": {"parameter_refs": ["PAR-SESSION-DURATION", "PAR-DEVICE-AGE"]}})
        n += 1
    pay_params = ["PAR-AMOUNT", "PAR-RAIL", "PAR-TIMING"]
    if pattern in {"aml", "velocity"}:
        pay_params.extend(["PAR-VELOCITY", "PAR-SEQUENCE-GAP"])
    if pattern == "velocity":
        pay_params.append("PAR-RETRY-COUNT")
    extras.append({"action_id": f"step-{n:02d}", "action_type": "initiate_payment", "parameters": {"parameter_refs": pay_params}})
    return setup + extras


def mutation_dimensions(pattern: str) -> list[str]:
    base = ["amount", "timing", "rail", "device_state"]
    extra = {
        "mule": ["beneficiary_novelty", "velocity"],
        "merchant": ["merchant_familiarity", "mcc"],
        "identity": ["trust_score", "account_age"],
        "aml": ["velocity", "sequence_gap", "threshold_hug"],
        "velocity": ["velocity", "sequence_gap", "retry_count"],
        "account": ["account_age"],
        "auth": ["session_duration", "device_age"],
        "payment_probe": ["amount"],
        "agentic": ["agent_goal"],
    }
    return base + extra.get(pattern, [])


def display_name(slug_name: str) -> str:
    return slug_name.replace("_", " ").strip()


def merge_variant_names(source_names: list[str], dataset_names: list[str]) -> list[tuple[str, str, str]]:
    """Return (display_name, slug, origin) without inventing extra variants.

    Source-backed names come from the legacy family JSON (PDF extract).
    Dataset-only names for the same family are implementation_derived.
    """
    seen_norm: dict[str, tuple[str, str, str]] = {}
    for raw in source_names:
        name = (raw or "").strip()
        if not name:
            continue
        key = norm(name)
        seen_norm[key] = (name, slug(name), "source_backed")
    for raw in dataset_names:
        name = display_name(raw)
        key = norm(name)
        if key in seen_norm:
            continue
        seen_norm[key] = (name, slug(raw), "implementation_derived")
    return list(seen_norm.values())


def map_signal_features(signal: dict[str, Any], known_features: set[str]) -> list[str]:
    blob = norm(" ".join([
        signal.get("name") or "",
        signal.get("category") or "",
        signal.get("description") or "",
        " ".join(signal.get("detection_methods") or []),
    ]))
    found: list[str] = []
    for keywords, features in FEATURE_KEYWORDS:
        if any(keyword in blob for keyword in keywords):
            found.extend(features)
    ordered: list[str] = []
    seen: set[str] = set()
    for feature in found:
        if feature in known_features and feature not in seen:
            seen.add(feature)
            ordered.append(feature)
    return ordered


def control_sandbox_key(control_name: str) -> str | None:
    text = norm(control_name)
    mapping = [
        (["velocity", "amount limit", "transaction anomal"], "payment_initiation"),
        (["beneficiary", "mule", "cash out", "cash-out"], "mule_cashout"),
        (["aml", "structuring", "sanctions", "pep"], "aml_compliance"),
        (["device", "emulator", "fingerprint", "bot"], "device_session"),
        (["merchant", "mcc", "acquirer", "kyb"], "merchant"),
        (["kyc", "identity", "synthetic identity", "document"], "identity_kyc"),
        (["authorization", "risk score", "challenge"], "authorization"),
    ]
    for keywords, key in mapping:
        if any(keyword in text for keyword in keywords):
            return key
    return None


def counterpart_for_pattern(pattern: str) -> list[str]:
    mapping = {
        "mule": ["LCP-0001"],
        "aml": ["LCP-0002"],
        "merchant": ["LCP-0003"],
        "velocity": ["LCP-0004"],
        "identity": ["LCP-0005"],
        "account": ["LCP-0005"],
        "auth": ["LCP-0001"],
        "payment_probe": ["LCP-0004"],
        "agentic": [],
    }
    return mapping.get(pattern, [])


def write_nested(nested: Path, payload: dict[str, Any]) -> None:
    dump_json(nested, payload)


def main() -> int:
    families_doc = load_json(CANONICAL / "attacks" / "attack_families.json")
    signals_doc = load_json(CANONICAL / "defense" / "signals.json")
    stages_doc = load_json(CANONICAL / "lifecycle" / "lifecycle_stages.json")
    controls_doc = load_json(CANONICAL / "defense" / "controls.json")
    evidence_doc = load_json(CANONICAL / "evidence" / "evidence.json")
    relationships_doc = load_json(CANONICAL / "attacks" / "attack_relationships.json")
    aliases_lifecycle = load_json(CANONICAL / "lifecycle" / "lifecycle_aliases.json")
    aliases_signal = load_json(CANONICAL / "defense" / "signal_aliases.json")
    legacy_families = load_json(LEGACY / "attack_families.json").get("attack_families", [])
    legacy_variant_names = {
        item["attack_id"]: [name for name in (item.get("variants") or []) if isinstance(name, str) and name.strip()]
        for item in legacy_families
        if item.get("attack_id")
    }

    families: list[dict[str, Any]] = deepcopy(families_doc["attack_families"])
    signals: list[dict[str, Any]] = deepcopy(signals_doc["signals"])
    stages: list[dict[str, Any]] = deepcopy(stages_doc["lifecycle_stages"])
    controls: list[dict[str, Any]] = deepcopy(controls_doc["controls"])
    evidence: list[dict[str, Any]] = deepcopy(evidence_doc["evidence"])
    seed_rel_types = {"occurs_at", "observes", "targets"}
    relationships: list[dict[str, Any]] = [
        item for item in deepcopy(relationships_doc["relationships"])
        if item.get("relationship_type") in seed_rel_types
    ]

    dataset = extract_dataset_config()
    dataset_variants: dict[str, list[str]] = {}
    dataset_only: list[dict[str, Any]] = []
    family_ids = {family["attack_id"] for family in families}
    for doc_key, doc in dataset.items():
        for family_id, spec in (doc.get("families") or {}).items():
            names = list(spec.get("variants") or [])
            if family_id in DATASET_ONLY_FAMILY_IDS or family_id not in family_ids:
                dataset_only.append({
                    "family_id": family_id,
                    "document_key": doc_key,
                    "dataset_filename": doc.get("filename"),
                    "variant_slugs": names,
                    "status": "review",
                    "reason": (
                        "Present in generate_dataset.py (and possibly known_fraud.csv) but not in the "
                        "57-family KB. merchant-6.pdf / payment-inititation-5.pdf did not yield family IDs "
                        "in page extraction. Not promoted into the Knowledge Base."
                    ),
                })
                continue
            dataset_variants[family_id] = names

    known_features: set[str] = set()
    if FEATURES_JSON.exists():
        known_features.update(load_json(FEATURES_JSON).get("feature_order") or [])
    known_features.update({
        "amount", "payment_rail", "transaction_type", "authentication_method",
        "card_present", "auth_success", "currency", "merchant_category_code",
        "merchant_risk_score", "merchant_familiarity_score", "device_age_days",
        "account_age_days", "is_new_device", "is_new_beneficiary", "velocity_score",
        "transaction_count_last_1h", "transaction_count_last_24h", "avg_amount_last_1d",
        "avg_amount_last_7d", "amount_to_avg_7d_ratio", "amount_zscore_account",
        "seconds_since_prev_tx", "distinct_beneficiaries_last_24h", "distinct_devices_last_7d",
        "account_tx_count_to_date", "campaign_step", "hour_of_day", "day_of_week", "is_night",
        "location_country", "location_region",
    })

    variants: list[dict[str, Any]] = []
    vectors: list[dict[str, Any]] = []
    extra_relationships: list[dict[str, Any]] = []
    rel_n = max(int(item["relationship_id"].split("-")[1]) for item in relationships) + 1

    def add_rel(from_ref: str, rel_type: str, to_ref: str, evidence_ids: list[str] | None = None) -> None:
        nonlocal rel_n
        extra_relationships.append({
            "relationship_id": f"REL-{rel_n:05d}",
            "from_ref": from_ref,
            "relationship_type": rel_type,
            "to_ref": to_ref,
            "evidence": evidence_ids or [],
        })
        rel_n += 1

    for family in families:
        attack_id = family["attack_id"]
        pattern = classify_pattern(family)
        executable = is_sandbox_executable(family)
        template_key = pattern if executable else "agentic"
        template = TEMPLATE_SPECS[template_key]
        caps = assign_capabilities(family)
        family["sandbox_executable"] = executable
        family["simulation_template_id"] = template["template_id"]
        family["genai"] = {
            "classification": family.get("genai_classification"),
            "load_bearing": family.get("genai_load_bearing"),
            "transformation": family.get("genai_transformation"),
            "capability_ids": caps,
        }
        names = merge_variant_names(legacy_variant_names.get(attack_id, []), dataset_variants.get(attack_id, []))
        variant_ids: list[str] = []
        for index, (name, variant_slug, origin) in enumerate(names, start=1):
            variant_id = f"VAR-{attack_id}-{index:02d}"
            variant_ids.append(variant_id)
            evidence_ids = [item for item in family.get("evidence") or [] if isinstance(item, str)]
            variants.append({
                "variant_id": variant_id,
                "family_id": attack_id,
                "name": name,
                "slug": variant_slug,
                "description": None,
                "origin": origin,
                "origin_note": (
                    "Copied from canonical family variants[] (PDF-backed family record)."
                    if origin == "source_backed"
                    else "Present in generate_dataset.py DOCUMENT_CONFIG for this family; not in the family JSON variant list. Marked implementation_derived."
                ),
                "sandbox_executable": executable,
                "evidence_ids": evidence_ids[:1],
            })
            add_rel(variant_id, "variant_of", attack_id, evidence_ids[:1])

            vector_id = f"VEC-{attack_id}-{index:02d}"
            actions = template_actions(template_key if executable else "agentic", executable)
            vectors.append({
                "vector_id": vector_id,
                "family_id": attack_id,
                "variant_id": variant_id,
                "variant_ref": variant_id,
                "objective": family.get("objective"),
                "lifecycle_stage_ids": [
                    item for item in [family.get("lifecycle_stage_id"), *family.get("cross_stage_lifecycle_stage_ids", [])]
                    if item
                ],
                "rails": allowed_rails(family, pattern),
                "channels": allowed_channels(pattern, family),
                "prerequisites": list(family.get("prerequisites") or []),
                "required_state": {
                    "entities": template["required_entities"],
                    "keys": template["required_state_keys"],
                },
                "ordered_actions": actions,
                "attacker_controlled_parameters": {
                    "parameter_ids": [item for item in template["parameter_ids"] if item != "PAR-ACCOUNT-AGE"]
                },
                "parameter_distribution_refs": template["parameter_ids"],
                "mutation_dimensions": mutation_dimensions(pattern if executable else "agentic"),
                "expected_observable_signal_ids": list(family.get("observable_signal_ids") or []),
                "targeted_control_ids": list(family.get("targeted_control_ids") or []),
                "success_conditions": [
                    "authorization_decision in {ALLOW, CHALLENGE} for payment steps" if executable
                    else "specification only — sandbox cannot execute this family yet"
                ],
                "failure_conditions": ["authorization_decision == BLOCK"] if executable else [],
                "legitimate_counterpart_ids": counterpart_for_pattern(pattern if executable else "agentic"),
                "edge_cases": [],
                "simulation_template_id": template["template_id"],
                "simulation_template_ref": template["template_id"],
                "state_requirement_id": f"SRQ-{template['template_id'][4:]}",
                "sandbox_executable": executable,
                "origin": origin,
                "evidence_ids": evidence_ids[:1],
                "evidence": [],
            })
            add_rel(vector_id, "instantiates", attack_id, evidence_ids[:1])
            add_rel(vector_id, "uses_template", template["template_id"])
            for counterpart_id in counterpart_for_pattern(pattern if executable else "agentic"):
                add_rel(vector_id, "has_counterpart", counterpart_id)
        family["variant_ids"] = variant_ids
        family["variants"] = [name for name, _, origin in names if origin == "source_backed"]

    templates = []
    state_requirements = []
    for pattern, spec in TEMPLATE_SPECS.items():
        req_id = f"SRQ-{spec['template_id'][4:]}"
        templates.append({
            "template_id": spec["template_id"],
            "name": spec["name"],
            "campaign_pattern": pattern,
            "required_entities": spec["required_entities"],
            "supported_action_types": spec["supported_action_types"],
            "required_state_keys": spec["required_state_keys"],
            "parameter_ids": spec["parameter_ids"],
            "state_requirement_id": req_id,
            "parameter_schema_ref": None,
            "constraints": [
                "Do not independently randomize amount, device, merchant, beneficiary, geo, and velocity.",
                "Sample legitimate baseline first, then mutate attacker-controllable parameters.",
            ],
            "origin": "implementation_derived",
            "evidence": [],
        })
        state_requirements.append({
            "requirement_id": req_id,
            "name": spec["name"] + " required state",
            "required_entities": spec["required_entities"],
            "required_state": {key: True for key in spec["required_state_keys"]},
            "notes": "Copied from current sandbox campaign-builder patterns. Not PDF-invented thresholds.",
            "origin": "implementation_derived",
        })

    mappings = []
    for index, signal in enumerate(signals, start=1):
        features = map_signal_features(signal, known_features)
        if not features:
            continue
        mapping_id = f"SFM-{index:04d}"
        mappings.append({
            "mapping_id": mapping_id,
            "signal_id": signal["signal_id"],
            "feature_names": features,
            "rationale": "Keyword overlap between signal text and FraudShield / sandbox feature names.",
            "origin": "implementation_derived",
            "confidence": "INFERRED",
        })
        add_rel(signal["signal_id"], "maps_to_feature", mapping_id)

    implemented = 0
    for control in controls:
        sandbox_key = control_sandbox_key(control.get("name") or "")
        if not sandbox_key:
            continue
        add_rel(control["control_id"], "implemented_by", f"sandbox:{sandbox_key}")
        implemented += 1

    relationships.extend(extra_relationships)

    now = datetime.now(timezone.utc).isoformat()
    catalog = {
        "registry_version": "2.0",
        "built_at": now,
        "layout": {
            "attacks": ["attack_families.json", "attack_variants.json", "attack_vectors.json", "attack_relationships.json"],
            "defense": ["signals.json", "controls.json", "signal_feature_mappings.json"],
            "lifecycle": ["lifecycle_stages.json", "lifecycle_aliases.json"],
            "simulation": ["simulation_templates.json", "parameters.json", "state_requirements.json", "legitimate_counterparts.json"],
            "genai": ["capabilities.json"],
            "evidence": ["evidence.json"],
        },
        "counts": {
            "attack_families": len(families),
            "attack_variants": len(variants),
            "attack_vectors": len(vectors),
            "signals": len(signals),
            "controls": len(controls),
            "lifecycle_stages": len(stages),
            "relationships": len(relationships),
            "evidence": len(evidence),
            "simulation_templates": len(templates),
            "simulation_parameters": len(PARAMETERS),
            "state_requirements": len(state_requirements),
            "legitimate_counterparts": len(COUNTERPARTS),
            "genai_capabilities": len(CAPABILITIES),
            "signal_feature_mappings": len(mappings),
            "dataset_only_family_ids": len(dataset_only),
        },
        "domain_law": [
            "KB is not a transaction database.",
            "KB is not generated attack rows.",
            "KB is not model training data.",
            "Vectors are specifications; instances are generated at runtime.",
            "Sandbox state, experiments, Red memory, buffer, training datasets, and model registry are separate domains.",
        ],
        "compat": {
            "runtime_files": [
                "data/knowledge/attack_families.json",
                "data/knowledge/attack_signals.json",
                "data/knowledge/lifecycle_stages.json",
            ],
            "runtime_files_are_canonical": True,
            "flat_canonical_copies": False,
            "enriched_families_not_promoted": True,
        },
    }

    family_payload = {"registry_version": "2.0", "built_at": now, "attack_families": families}
    variant_payload = {"registry_version": "2.0", "built_at": now, "attack_variants": variants}
    vector_payload = {"registry_version": "2.0", "built_at": now, "attack_vectors": vectors}
    rel_payload = {"registry_version": "2.0", "built_at": now, "relationships": relationships}
    signal_payload = {**signals_doc, "registry_version": "2.0"}
    control_payload = {**controls_doc, "registry_version": "2.0"}
    stage_payload = {**stages_doc, "registry_version": "2.0"}
    evidence_payload = {**evidence_doc, "registry_version": "2.0"}
    mapping_payload = {"registry_version": "2.0", "built_at": now, "signal_feature_mappings": mappings}
    template_payload = {"registry_version": "2.0", "built_at": now, "simulation_templates": templates}
    param_payload = {"registry_version": "2.0", "built_at": now, "parameters": PARAMETERS}
    req_payload = {"registry_version": "2.0", "built_at": now, "state_requirements": state_requirements}
    counterpart_payload = {"registry_version": "2.0", "built_at": now, "legitimate_counterparts": COUNTERPARTS}
    cap_payload = {"registry_version": "2.0", "built_at": now, "capabilities": CAPABILITIES}

    write_nested(CANONICAL / "attacks" / "attack_families.json", family_payload)
    write_nested(CANONICAL / "attacks" / "attack_variants.json", variant_payload)
    write_nested(CANONICAL / "attacks" / "attack_vectors.json", vector_payload)
    write_nested(CANONICAL / "attacks" / "attack_relationships.json", rel_payload)
    write_nested(CANONICAL / "defense" / "signals.json", signal_payload)
    write_nested(CANONICAL / "defense" / "controls.json", control_payload)
    write_nested(CANONICAL / "defense" / "signal_feature_mappings.json", mapping_payload)
    write_nested(CANONICAL / "lifecycle" / "lifecycle_stages.json", stage_payload)
    dump_json(CANONICAL / "lifecycle" / "lifecycle_aliases.json", aliases_lifecycle)
    dump_json(CANONICAL / "defense" / "signal_aliases.json", aliases_signal)
    write_nested(CANONICAL / "simulation" / "simulation_templates.json", template_payload)
    write_nested(CANONICAL / "simulation" / "parameters.json", param_payload)
    write_nested(CANONICAL / "simulation" / "state_requirements.json", req_payload)
    write_nested(CANONICAL / "simulation" / "legitimate_counterparts.json", counterpart_payload)
    write_nested(CANONICAL / "genai" / "capabilities.json", cap_payload)
    write_nested(CANONICAL / "evidence" / "evidence.json", evidence_payload)
    dump_json(CANONICAL / "catalog.json", catalog)

    signal_by_id = {item["signal_id"]: item for item in signals if item.get("signal_id")}
    stage_by_id = {item["stage_id"]: item for item in stages if item.get("stage_id")}
    control_by_id = {item["control_id"]: item for item in controls if item.get("control_id")}
    runtime_families = []
    for family in families:
        record = deepcopy(family)
        stage = stage_by_id.get(record.get("lifecycle_stage_id") or "")
        record["lifecycle_stage"] = (stage or {}).get("name") or ""
        record["detection_signals"] = [
            {
                "signal_id": signal_id,
                "name": (signal_by_id.get(signal_id) or {}).get("name"),
                "detection_method": "; ".join((signal_by_id.get(signal_id) or {}).get("detection_methods") or []),
            }
            for signal_id in record.get("observable_signal_ids") or []
            if signal_id in signal_by_id
        ]
        record["controls_targeted"] = [
            (control_by_id.get(control_id) or {}).get("name")
            for control_id in record.get("targeted_control_ids") or []
            if control_id in control_by_id and (control_by_id.get(control_id) or {}).get("name")
        ]
        record["evidence_confidence"] = record.get("confidence") or "UNVERIFIED"
        runtime_families.append(record)
    runtime_signals = []
    for signal in signals:
        record = deepcopy(signal)
        record["signal_name"] = record.get("name")
        record["detection_method"] = "; ".join(record.get("detection_methods") or [])
        runtime_signals.append(record)
    runtime_stages = []
    for stage in stages:
        record = deepcopy(stage)
        record["stage_name"] = record.get("name")
        record["stage"] = record.get("name")
        runtime_stages.append(record)
    dump_json(LEGACY / "attack_families.json", {
        "registry_version": "2.0",
        "built_at": now,
        "source": "data/knowledge/canonical/attacks/attack_families.json",
        "total_families": len(runtime_families),
        "attack_families": runtime_families,
    })
    dump_json(LEGACY / "attack_signals.json", {
        "registry_version": "2.0",
        "built_at": now,
        "source": "data/knowledge/canonical/defense/signals.json",
        "total_signals": len(runtime_signals),
        "signals": runtime_signals,
    })
    dump_json(LEGACY / "lifecycle_stages.json", {
        "registry_version": "2.0",
        "built_at": now,
        "source": "data/knowledge/canonical/lifecycle/lifecycle_stages.json",
        "total_stages": len(runtime_stages),
        "lifecycle_stages": runtime_stages,
    })

    review_queue_path = LEGACY / "review" / "dataset_only_families.json"
    dump_json(review_queue_path, {
        "status": "review",
        "built_at": now,
        "families": dataset_only,
    })

    origin_counts = defaultdict(int)
    for variant in variants:
        origin_counts[variant["origin"]] += 1
    genai_counts = defaultdict(int)
    for family in families:
        genai_counts[str(family.get("genai_classification"))] += 1
    executable_families = sum(1 for family in families if family.get("sandbox_executable"))
    executable_vectors = sum(1 for vector in vectors if vector.get("sandbox_executable"))

    print("Complete knowledge model")
    print(f"  families: {len(families)} (sandbox-executable {executable_families})")
    print(f"  variants: {len(variants)} source_backed={origin_counts['source_backed']} implementation_derived={origin_counts['implementation_derived']}")
    print(f"  vectors: {len(vectors)} (sandbox-executable {executable_vectors})")
    print(f"  signals: {len(signals)} mappings: {len(mappings)}")
    print(f"  controls: {len(controls)} implemented_by edges: {implemented}")
    print(f"  relationships: {len(relationships)}")
    print(f"  templates: {len(templates)} parameters: {len(PARAMETERS)} counterparts: {len(COUNTERPARTS)}")
    print(f"  genai capabilities: {len(CAPABILITIES)} family classes: {dict(genai_counts)}")
    print(f"  dataset-only family IDs held in review: {len(dataset_only)}")
    print(f"  published runtime KB: {LEGACY / 'attack_families.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
