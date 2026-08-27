"""
Complete Fraud Dataset Generator for Mastercard Innovation Challenge 2026
Generates synthetic transaction data for all 15 payment fraud taxonomies

Total: 67 attack families, 100,000 training rows (50/50 split)
"""

import json
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any

from realism import apply_realism

# ============================================================
# CONFIGURATION - ALL 15 DOCUMENTS (SCALED TO 100K)
# ============================================================

TOTAL_ROWS = 100000
FRAUD_ROWS = TOTAL_ROWS // 2
LEGIT_ROWS = TOTAL_ROWS // 2

DOCUMENT_CONFIG = {
    # Document 1: agent-commerce-11.pdf (5 families)
    "agent_commerce": {
        "filename": "agent_commerce_dataset.json",
        "total_rows": 9000,
        "fraud_rows": 4500,
        "legit_rows": 4500,
        "families": {
            "AG-001": {"rows": 900, "variants": ["Merchant_Side_Manipulation", "Visual_Prompt_Injection", "Unauthorized_Tool_Calls", "Agent_Mediated_Payment_Fraud", "Agentic_Carding"]},
            "AG-002": {"rows": 900, "variants": ["Agent_Identity_Theft", "Agent_Social_Engineering", "Agentic_Account_Takeover", "Shopping_Manipulation", "Synthetic_Identity_Farming"]},
            "AG-003": {"rows": 900, "variants": ["Sleeper_Memory_Poisoning", "Environment_Injected_Poisoning", "Cross_Session_Context_Injection"]},
            "AG-004": {"rows": 900, "variants": ["Agent_Session_Smuggling", "Cross_Agent_Privilege_Escalation", "A2A_Injection", "Agent_Delegation_Abuse"]},
            "AG-005": {"rows": 900, "variants": ["Self_Evolving_Fraud", "Adaptive_Evasion", "Agentic_Fraud_Optimization", "Real_Time_Strategy_Adaptation"]}
        }
    },
    
    # Document 2: aml-14.pdf (6 families)
    "aml": {
        "filename": "aml_dataset.json",
        "total_rows": 8100,
        "fraud_rows": 4050,
        "legit_rows": 4050,
        "families": {
            "AML-001": {"rows": 675, "variants": ["Pattern_Free_Movement", "Behavioral_Camouflage", "Risk_Score_Manipulation", "Threshold_Conscious_Structuring", "Adaptive_Pattern_Generation"]},
            "AML-002": {"rows": 675, "variants": ["False_Positive_Flooding", "Alert_System_Overload", "Investigator_Overwhelm", "Synthetic_Alert_Generation", "Mass_False_Positive_Generation"]},
            "AML-003": {"rows": 675, "variants": ["Synthetic_Transaction_Narratives", "Fabricated_Business_Justification", "AI_Generated_Customer_Communications", "Fabricated_Supporting_Documentation"]},
            "AML-004": {"rows": 675, "variants": ["Identity_Obfuscation", "Name_Variation_Generation", "Entity_Concealment", "Beneficial_Ownership_Concealment"]},
            "AML-005": {"rows": 675, "variants": ["Investigator_Impersonation", "AI_Generated_Investigation_Responses", "Compliance_Workflow_Manipulation", "Evidence_Fabrication"]},
            "AML-006": {"rows": 675, "variants": ["Training_Data_Poisoning", "Label_Flipping", "Adversarial_Sample_Injection", "Model_Evasion", "Backdoor_Insertion"]}
        }
    },
    
    # Document 3: acquirer-7.pdf (4 families)
    "acquirer": {
        "filename": "acquirer_dataset.json",
        "total_rows": 6300,
        "fraud_rows": 3150,
        "legit_rows": 3150,
        "families": {
            "ACQ-001": {"rows": 788, "variants": ["Synthetic_Business_Fraud", "Merchant_Impersonation", "UBO_Director_Fraud", "MATCH_List_Evasion", "Acquirer_Data_Manipulation"]},
            "ACQ-002": {"rows": 787, "variants": ["Transaction_Pattern_Optimization", "Risk_Score_Evasion", "Behavioral_Camouflage", "Adaptive_Pattern_Generation", "Threshold_Avoidance"]},
            "ACQ-003": {"rows": 787, "variants": ["Merchant_Portfolio_Abuse", "Merchant_Aggregation", "PayFac_Sub_Merchant_Exploitation", "Synthetic_Merchant_Portfolios", "Fraud_Rings"]},
            "ACQ-004": {"rows": 788, "variants": ["Front_Merchant_Fraud", "Website_Content_Misrepresentation", "Business_Description_Fabrication", "AI_Generated_Merchant_Websites", "Content_Cloaking"]}
        }
    },
    
    # Document 4: authentication-4.pdf (4 families)
    "authentication": {
        "filename": "authentication_dataset.json",
        "total_rows": 7200,
        "fraud_rows": 3600,
        "legit_rows": 3600,
        "families": {
            "AUTH-001": {"rows": 900, "variants": ["Email_Phishing", "SMS_Phishing", "Social_Media_Phishing", "Spear_Phishing", "BEC", "AitM_Phishing"]},
            "AUTH-002": {"rows": 900, "variants": ["Voice_Cloning_Vishing", "Bank_Official_Impersonation", "Law_Enforcement_Impersonation", "Digital_Arrest_Scam", "Family_Impersonation"]},
            "AUTH-003": {"rows": 900, "variants": ["Document_Based_Recovery", "Voice_Based_Recovery", "Video_Based_Recovery", "Customer_Support_Impersonation", "Hybrid_Recovery"]},
            "AUTH-004": {"rows": 900, "variants": ["Keystroke_Injection", "Facial_Injection", "Voice_Cloning", "Motion_Forecasting", "Synthetic_Fingerprint_Iris"]}
        }
    },
    
    # Document 5: authorization-10.pdf (3 families)
    "authorization": {
        "filename": "authorization_dataset.json",
        "total_rows": 5400,
        "fraud_rows": 2700,
        "legit_rows": 2700,
        "families": {
            "AUT-001": {"rows": 900, "variants": ["Transaction_Splitting", "Velocity_Check_Evasion", "Low_And_Slow_Fraud", "Threshold_Conscious_Optimization", "Adaptive_Timing_Manipulation"]},
            "AUT-002": {"rows": 900, "variants": ["Model_Boundary_Exploration", "Feature_Optimization", "Model_Probing", "Black_Box_Surrogate_Modeling", "Decision_Boundary_Exploitation"]},
            "AUT-003": {"rows": 900, "variants": ["Multi_Account_Coordinated_Fraud", "Synthetic_Account_Farming", "Parallel_Fraud_Operations", "Coordinated_Bust_Out_Networks", "Fraud_Mesh_Orchestration"]}
        }
    },
    
    # Document 6: cash-out-13.pdf (4 families)
    "cash_out": {
        "filename": "cash_out_dataset.json",
        "total_rows": 7200,
        "fraud_rows": 3600,
        "legit_rows": 3600,
        "families": {
            "CM-001": {"rows": 900, "variants": ["Personalized_Recruitment", "Deepfake_Video_Recruitment", "Fake_Job_Recruitment", "Romance_Scam_Recruitment", "Coerced_Recruitment", "Unwitting_Exploitation"]},
            "CM-002": {"rows": 900, "variants": ["Synthetic_Identity_Farming", "AI_Generated_Document_Fraud", "Account_Farming_As_A_Service", "Bulk_Account_Creation", "Seasoned_Account_Inventory"]},
            "CM-003": {"rows": 900, "variants": ["Agentic_Orchestration", "Pattern_Free_Layering", "Cross_Institution_Coordination", "Mule_As_A_Service", "Multi_Hop_Layering", "Adaptive_Transaction_Pattern_Evasion"]},
            "CM-004": {"rows": 900, "variants": ["Cross_Chain_Crypto_Laundering", "Stablecoin_Conversion", "AI_Optimized_Exchange_Selection", "ATM_Cash_Out", "Asset_Purchase_Monetization"]}
        }
    },
    
    # Document 7: device-session-3.pdf (5 families)
    "device_session": {
        "filename": "device_session_dataset.json",
        "total_rows": 8100,
        "fraud_rows": 4050,
        "legit_rows": 4050,
        "families": {
            "DFS-001": {"rows": 810, "variants": ["Browser_Automation", "Kernel_Level_Spoofing", "AI_Anti_Detection", "Data_Wiping_Reset"]},
            "EFF-001": {"rows": 810, "variants": ["Virtual_Emulator_Farm", "Cloud_Phone_Farm", "Physical_Device_Farm", "AI_Orchestrated_Farm"]},
            "RAT-001": {"rows": 810, "variants": ["ATS_RAT", "Behavioral_Mimicry_RAT", "AI_Distributed_RAT", "NFC_Relay_RAT"]},
            "BOT-001": {"rows": 810, "variants": ["Credential_Stuffing", "Card_Testing", "Account_Creation_Bot", "Autonomous_Agent_Fraud"]},
            "BBE-001": {"rows": 810, "variants": ["Keystroke_Injection", "Robot_Adversarial", "Motion_Forecasting", "Adversarial_Behavioral"]}
        }
    },
    
    # Document 8: gateway-processor-8.pdf (7 families)
    "gateway_processor": {
        "filename": "gateway_processor_dataset.json",
        "total_rows": 9000,
        "fraud_rows": 4500,
        "legit_rows": 4500,
        "families": {
            "GP-001": {"rows": 643, "variants": ["Payment_Amount_Manipulation", "Prompt_Injection", "Currency_Manipulation", "Merchant_ID_Manipulation"]},
            "GP-002": {"rows": 643, "variants": ["Stripe_Webhook_Bypass", "PayPal_IPN_Forgery", "LLM_Gateway_Webhook_Exploitation", "Quota_Fraud"]},
            "GP-003": {"rows": 643, "variants": ["BIN_Attacks", "Authorization_Abuse", "AI_Powered_Validation_Platforms", "Distributed_Card_Testing"]},
            "GP-004": {"rows": 643, "variants": ["x402_Protocol_Attacks", "AP2_Protocol_Exploitation", "Replay_Idempotency_Attacks", "Header_Proxy_Confusion"]},
            "GP-005": {"rows": 643, "variants": ["Payment_Redirection", "Processor_Selection_Manipulation", "Malicious_Agent_Routing"]},
            "GP-006": {"rows": 643, "variants": ["AI_Assistant_Credential_Theft", "Stored_Payment_Token_Abuse", "Agent_Hijacking", "Malicious_Website_Poisoning"]},
            "GP-007": {"rows": 642, "variants": ["Rapid_Agent_Shopping", "High_Velocity_Transaction_Bursts", "Distributed_AI_Agent_Fraud"]}
        }
    },
    
    # Document 9: KYC-1.pdf (5 families)
    "kyc": {
        "filename": "kyc_dataset.json",
        "total_rows": 8100,
        "fraud_rows": 4050,
        "legit_rows": 4050,
        "families": {
            "SIF-001": {"rows": 810, "variants": ["Synthetic_Identity_Creation", "Credit_Building", "Bust_Out", "Mule_Account"]},
            "GDF-001": {"rows": 810, "variants": ["Passport_Forgery", "DL_Forgery", "National_ID_Forgery", "Utility_Bill_Forgery"]},
            "DII-001": {"rows": 810, "variants": ["Camera_Injection", "Face_Swap", "Voice_Cloning", "Synthetic_Biometrics"]},
            "SEP-001": {"rows": 810, "variants": ["Phishing", "Vishing", "Romance_Scam", "Digital_Arrest", "BEC"]},
            "ATO-001": {"rows": 810, "variants": ["Password_Reset_Impersonation", "Security_Question_Bypass", "Customer_Support_Impersonation"]}
        }
    },
    
    # Document 10: merchant-6.pdf (6 families)
    "merchant": {
        "filename": "merchant_dataset.json",
        "total_rows": 9000,
        "fraud_rows": 4500,
        "legit_rows": 4500,
        "families": {
            "MCH-001": {"rows": 750, "variants": ["Synthetic_Business_Fraud", "Merchant_Impersonation", "MCC_Fraud", "Synthetic_UBO_Director_Fraud", "Hybrid_Synthetic"]},
            "MCH-002": {"rows": 750, "variants": ["Front_Merchant_Fraud", "Transaction_Laundering_Fronts", "Shell_Company_Networks", "Commercial_Laundering"]},
            "MCH-003": {"rows": 750, "variants": ["Scam_Merchant_Storefronts", "Brand_Impersonation_Stores", "Fake_Ecommerce_Stores", "Triangulation_Fraud"]},
            "MCH-004": {"rows": 750, "variants": ["Commercial_Laundering", "Network_Laundering", "Front_Merchant_Laundering"]},
            "MCH-005": {"rows": 750, "variants": ["Fake_Damage_Images", "Fake_Damage_Videos", "Product_Defect_Fabrication", "Organized_Refund_Rings"]},
            "MCH-006": {"rows": 750, "variants": ["Merchant_Phishing", "Deepfake_Impersonation", "Voice_Cloning_Attacks", "Customer_Impersonation"]}
        }
    },
    
    # Document 11: network-15.pdf (4 families)
    "network": {
        "filename": "network_dataset.json",
        "total_rows": 6300,
        "fraud_rows": 3150,
        "legit_rows": 3150,
        "families": {
            "N-001": {"rows": 788, "variants": ["Synthetic_Identity_Fabric", "AI_Generated_Identity_Clusters", "Account_Farming_Networks", "Synthetic_Identity_Rings"]},
            "N-002": {"rows": 787, "variants": ["Human_Assisted_Fraud_Rings", "AI_Agent_Orchestrated_Rings", "Multi_Scam_Rings"]},
            "N-003": {"rows": 787, "variants": ["End_To_End_Autonomous_Campaigns", "AI_Planned_Bust_Out_Campaigns", "Agentic_Fraud_Operations"]},
            "N-004": {"rows": 788, "variants": ["Banking_To_Crypto_Laundering", "Multi_Blockchain_Routing", "Cross_Chain_Bridge_Exploitation", "AI_Optimized_Cross_Rail_Movement"]}
        }
    },
    
    # Document 12: onboarding-2.pdf (3 families)
    "onboarding": {
        "filename": "onboarding_dataset.json",
        "total_rows": 4500,
        "fraud_rows": 2250,
        "legit_rows": 2250,
        "families": {
            "SIA-001": {"rows": 750, "variants": ["Credit_Building_Bust_Out", "Mule_Account_Creation", "Identity_Farming", "Mass_Bot_Creation"]},
            "MDF-001": {"rows": 750, "variants": ["Income_Misrepresentation", "Employment_Fabrication", "Address_Falsification", "Synthetic_Financial_History"]},
            "ATO-002": {"rows": 750, "variants": ["Deepfake_Biometric_Bypass", "Document_Recovery_Fraud", "Customer_Support_Impersonation", "OTP_SIM_Swap"]}
        }
    },
    
    # Document 13: open-banking-12.pdf (6 families)
    "open_banking": {
        "filename": "open_banking_dataset.json",
        "total_rows": 6300,
        "fraud_rows": 3150,
        "legit_rows": 3150,
        "families": {
            "OB-001": {"rows": 525, "variants": ["Single_Consent_Exploitation", "Broad_Scope_Abuse", "Consent_Deception", "Fine_Print_Exploitation", "Consent_Phishing"]},
            "OB-002": {"rows": 525, "variants": ["Counterfeit_Fintech_Apps", "Fake_Aggregators", "Brand_Impersonation", "Front_Business_TPPs", "App_Store_Fraud"]},
            "OB-003": {"rows": 525, "variants": ["TPP_Credential_Theft", "TPP_API_Key_Compromise", "Insider_TPP_Compromise", "Third_Party_Breach", "API_Endpoint_Exploitation"]},
            "OB-004": {"rows": 525, "variants": ["OAuth_Token_Theft", "Refresh_Token_Abuse", "Access_Token_Replay", "MITM_Token_Interception", "Credential_Replay"]},
            "OB-005": {"rows": 525, "variants": ["Scope_Creep", "Permission_Misuse", "Broad_Scope_Exploitation", "Unauthorized_Data_Access", "Permission_Escalation"]},
            "OB-006": {"rows": 525, "variants": ["Financial_Data_Harvesting", "Transaction_History_Exfiltration", "Balance_Monitoring", "Account_Aggregation_Abuse", "Financial_Profiling"]}
        }
    },
    
    # Document 14: payment-initiation-5.pdf (4 families)
    "payment_initiation": {
        "filename": "payment_initiation_dataset.json",
        "total_rows": 7200,
        "fraud_rows": 3600,
        "legit_rows": 3600,
        "families": {
            "PI-F001": {"rows": 900, "variants": ["Payment_Redirection", "BEC_Payment_Fraud", "Invoice_Fraud", "QR_Code_Manipulation", "Beneficiary_Substitution"]},
            "PI-F002": {"rows": 900, "variants": ["Investment_Scam", "Romance_Scam", "Impersonation_Scam", "Digital_Arrest_Scam", "Purchase_Scam", "Advance_Fee_Fraud"]},
            "PI-F003": {"rows": 900, "variants": ["Fake_Damage_Images", "Fake_Damage_Videos", "Wardrobing", "Receipt_Manipulation"]},
            "PI-F004": {"rows": 900, "variants": ["Synthetic_Merchant_Storefront", "Fake_Merchant_Onboarding", "AI_Generated_Merchant_Website", "Merchant_Collusion"]}
        }
    },
    
    # Document 15: payment-rail-9.pdf (1 family)
    "payment_rail": {
        "filename": "payment_rail_dataset.json",
        "total_rows": 5400,
        "fraud_rows": 2700,
        "legit_rows": 2700,
        "families": {
            "R-001": {"rows": 2700, "variants": ["SWIFT_MT_MX_Message_Injection", "Hyper_Personalized_Phishing", "Deepfake_Voice_Verification_Bypass", "AI_Generated_Bank_Correspondence"]}
        }
    }
}

# ============================================================
# JSON OUTPUT
# ============================================================

# Indented, one field per line, so the files are readable in an editor.
# Indenting costs only ~30% more bytes here, not the 3x you might expect: with
# 51 fields per transaction, most of the payload is field names rather than
# whitespace. Set COMPACT_JSON = True (or pass --compact) to write everything on
# one line instead, for when size or parse speed actually matters.
COMPACT_JSON = False

# One transaction per line: indented enough to scan vertically, without the
# 3x size penalty of fully expanding every field. Set via --per-line.
ONE_TX_PER_LINE = False


def _write_json(filename: str, output: Dict[str, Any]):
    with open(filename, 'w', encoding='utf-8') as f:
        if COMPACT_JSON:
            json.dump(output, f, separators=(',', ':'))
        elif ONE_TX_PER_LINE:
            # Hand-rolled so each transaction stays on a single line while the
            # surrounding structure is still readable.
            info = json.dumps(output["dataset_info"], indent=4)
            f.write('{\n  "dataset_info": ' + info.replace('\n', '\n  ') + ',\n')
            f.write('  "transactions": [\n')
            rows = output["transactions"]
            for i, tx in enumerate(rows):
                f.write('    ' + json.dumps(tx)
                        + (',\n' if i < len(rows) - 1 else '\n'))
            f.write('  ]\n}\n')
        else:
            json.dump(output, f, indent=2)


# ============================================================
# BASE GENERATOR CLASS
# ============================================================

class BaseGenerator:
    """Base class for generating transaction data"""
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
    
    def _generate_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    
    def _random_date(self, days_back: int = 90) -> str:
        date = datetime.now() - timedelta(days=random.randint(0, days_back))
        return date.isoformat()
    
    def _random_amount(self, min_val: float, max_val: float) -> float:
        return round(random.uniform(min_val, max_val), 2)
    
    def _random_choice(self, choices: List[str]) -> str:
        return random.choice(choices)
    
    def _base_transaction(self) -> Dict[str, Any]:
        return {
            "transaction_id": self._generate_id("txn"),
            "timestamp": self._random_date(90),
            "account_id": self._generate_id("acc"),
            "device_id": self._generate_id("dev"),
            "session_id": self._generate_id("ses"),
            "amount": 0.0,
            "currency": "INR",
            "merchant_id": None,
            "merchant_category_code": 0,
            "merchant_risk_score": 0.0,
            "payment_rail": "unknown",
            "transaction_type": "unknown",
            "card_present": False,
            "ip_address": "127.0.0.1",
            "location_country": "IN",
            "location_region": random.choice(["MH", "KA", "TN", "DL", "UP", "GJ", "RJ", "WB"]),
            "authentication_method": "unknown",
            "auth_success": False,
            "user_agent": "Mozilla/5.0",
            "beneficiary_account_id": None,
            "beneficiary_merchant_id": None,
            "beneficiary_is_new": False,
            "avg_amount_last_1d": 0.0,
            "avg_amount_last_7d": 0.0,
            "transaction_count_last_1h": 0,
            "transaction_count_last_24h": 0,
            "device_age_days": random.randint(1, 365),
            "account_age_days": random.randint(1, 730),
            "is_new_device": False,
            "is_new_beneficiary": False,
            "velocity_score": random.uniform(0, 1),
            "merchant_familiarity_score": random.uniform(0, 1),
            "campaign_id": None,
            "campaign_step": 0,
            "is_fraud": 0,
            "attack_family": None,
            "attack_variant": None,
            "lifecycle_stage": None
        }
    
    def _set_common_fraud_attributes(self, tx: Dict, family: str, variant: str, lifecycle: str) -> Dict:
        tx["is_fraud"] = 1
        tx["attack_family"] = family
        tx["attack_variant"] = variant
        tx["lifecycle_stage"] = lifecycle
        return tx


# ============================================================
# LEGITIMATE TRANSACTION GENERATOR
# ============================================================

class LegitimateGenerator(BaseGenerator):
    """Generate legitimate (non-fraud) transactions"""
    
    def generate(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        for _ in range(count):
            tx = self._base_transaction()
            tx["is_fraud"] = 0
            tx["attack_family"] = None
            tx["attack_variant"] = None
            tx["lifecycle_stage"] = random.choice([
                "Identity_KYC", "Account_Creation", "Device_Session", "Authentication",
                "Payment_Initiation", "Merchant", "Acquirer", "Gateway_Processor",
                "Authorization", "Settlement", "Cash_Out"
            ])
            tx["amount"] = self._random_amount(100, 50000)
            tx["payment_rail"] = random.choice(["card", "upi", "bank_transfer", "wallet"])
            tx["transaction_type"] = random.choice(["purchase", "bill_payment", "transfer", "salary_deposit", "subscription", "refund"])
            tx["auth_success"] = True
            tx["authentication_method"] = random.choice(["password", "otp", "biometric"])
            tx["card_present"] = random.choice([True, False])
            tx["merchant_risk_score"] = random.uniform(0, 0.3)
            tx["is_new_device"] = random.random() < 0.05
            tx["is_new_beneficiary"] = random.random() < 0.02
            # Historical aggregates must be calculated from prior transactions,
            # never from the transaction currently being generated.
            tx["avg_amount_last_1d"] = 0.0
            tx["avg_amount_last_7d"] = 0.0
            tx["transaction_count_last_1h"] = 0
            tx["transaction_count_last_24h"] = 0
            tx["velocity_score"] = random.uniform(0, 0.3)
            tx["merchant_familiarity_score"] = random.uniform(0.3, 1.0)
            
            if tx["transaction_type"] in ["purchase", "subscription"]:
                tx["merchant_id"] = self._generate_id("mch")
                tx["merchant_category_code"] = random.choice([5411, 5812, 5732, 5311, 5814])
            
            transactions.append(tx)
        return transactions


# ============================================================
# FRAUD GENERATORS FOR EACH FAMILY
# ============================================================

class FraudGenerator(BaseGenerator):
    """Generate fraud transactions for all attack families"""
    
    # -------- AG-001: Prompt Injection / Goal Hijacking --------
    def generate_ag_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["agent_commerce"]["families"]["AG-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AG-001", random.choice(variants), "AI_Agent_Commerce"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = random.choice(["card", "upi", "bank_transfer"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.7, 0.95)
            tx["merchant_risk_score"] = random.uniform(0.5, 0.9)
            tx["campaign_id"] = f"camp_ag001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    # -------- AG-002: Agent Impersonation --------
    def generate_ag_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["agent_commerce"]["families"]["AG-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AG-002", random.choice(variants), "AI_Agent_Commerce"
            )
            tx["amount"] = self._random_amount(1000, 1000000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["authentication_method"] = "biometric"
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["merchant_risk_score"] = random.uniform(0.4, 0.8)
            tx["campaign_id"] = f"camp_ag002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    # -------- AG-003: Memory Poisoning --------
    def generate_ag_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["agent_commerce"]["families"]["AG-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AG-003", random.choice(variants), "AI_Agent_Commerce"
            )
            tx["amount"] = self._random_amount(1000, 200000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.5, 0.85)
            tx["merchant_risk_score"] = random.uniform(0.3, 0.7)
            tx["campaign_id"] = f"camp_ag003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    # -------- AG-004: Agent-to-Agent Attacks --------
    def generate_ag_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["agent_commerce"]["families"]["AG-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AG-004", random.choice(variants), "AI_Agent_Commerce"
            )
            tx["amount"] = self._random_amount(500, 300000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi", "card"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["merchant_risk_score"] = random.uniform(0.4, 0.85)
            tx["campaign_id"] = f"camp_ag004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    # -------- AG-005: Autonomous Adaptive Fraud --------
    def generate_ag_005(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["agent_commerce"]["families"]["AG-005"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AG-005", random.choice(variants), "AI_Agent_Commerce"
            )
            tx["amount"] = self._random_amount(500, 500000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi", "crypto"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.7, 0.95)
            tx["merchant_risk_score"] = random.uniform(0.3, 0.8)
            tx["campaign_id"] = f"camp_ag005_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- AML-001 to AML-006 --------
    def generate_aml_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["aml"]["families"]["AML-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AML-001", random.choice(variants), "AML_Compliance"
            )
            tx["amount"] = self._random_amount(100, 100000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi", "card"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = random.random() < 0.5
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.1, 0.4)
            tx["merchant_risk_score"] = random.uniform(0, 0.3)
            tx["campaign_id"] = f"camp_aml001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_aml_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["aml"]["families"]["AML-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AML-002", random.choice(variants), "AML_Compliance"
            )
            tx["amount"] = self._random_amount(1000, 50000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = random.random() < 0.5
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["merchant_risk_score"] = random.uniform(0.5, 0.9)
            tx["campaign_id"] = f"camp_aml002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_aml_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["aml"]["families"]["AML-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AML-003", random.choice(variants), "AML_Compliance"
            )
            tx["amount"] = self._random_amount(1000, 200000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.3, 0.7)
            tx["merchant_risk_score"] = random.uniform(0.2, 0.6)
            tx["campaign_id"] = f"camp_aml003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_aml_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["aml"]["families"]["AML-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AML-004", random.choice(variants), "AML_Compliance"
            )
            tx["amount"] = self._random_amount(1000, 1000000)
            tx["payment_rail"] = random.choice(["bank_transfer", "crypto"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("sanctions_entity")
            tx["velocity_score"] = random.uniform(0.3, 0.7)
            tx["merchant_risk_score"] = random.uniform(0.6, 0.95)
            tx["campaign_id"] = f"camp_aml004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_aml_005(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["aml"]["families"]["AML-005"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AML-005", random.choice(variants), "AML_Compliance"
            )
            tx["amount"] = self._random_amount(1000, 300000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.4, 0.8)
            tx["merchant_risk_score"] = random.uniform(0.2, 0.5)
            tx["campaign_id"] = f"camp_aml005_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_aml_006(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["aml"]["families"]["AML-006"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AML-006", random.choice(variants), "AML_Compliance"
            )
            tx["amount"] = self._random_amount(100, 50000)
            tx["payment_rail"] = random.choice(["card", "upi", "bank_transfer"])
            tx["transaction_type"] = random.choice(["purchase", "transfer"])
            tx["auth_success"] = True
            tx["velocity_score"] = random.uniform(0.1, 0.4)
            tx["merchant_risk_score"] = random.uniform(0, 0.3)
            tx["campaign_id"] = f"camp_aml006_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- ACQ-001 to ACQ-004 --------
    def generate_acq_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["acquirer"]["families"]["ACQ-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "ACQ-001", random.choice(variants), "Acquirer"
            )
            tx["amount"] = self._random_amount(1000, 1000000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("synthetic_mch")
            tx["merchant_risk_score"] = random.uniform(0.7, 0.95)
            tx["campaign_id"] = f"camp_acq001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_acq_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["acquirer"]["families"]["ACQ-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "ACQ-002", random.choice(variants), "Acquirer"
            )
            tx["amount"] = self._random_amount(100, 50000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_risk_score"] = random.uniform(0, 0.3)
            tx["velocity_score"] = random.uniform(0.1, 0.4)
            tx["campaign_id"] = f"camp_acq002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_acq_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["acquirer"]["families"]["ACQ-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "ACQ-003", random.choice(variants), "Acquirer"
            )
            tx["amount"] = self._random_amount(1000, 200000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("mch_network")
            tx["merchant_risk_score"] = random.uniform(0.4, 0.8)
            tx["campaign_id"] = f"camp_acq003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_acq_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["acquirer"]["families"]["ACQ-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "ACQ-004", random.choice(variants), "Acquirer"
            )
            tx["amount"] = self._random_amount(100, 100000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("mch_misrep")
            tx["merchant_category_code"] = random.choice([5411, 5812])
            tx["merchant_risk_score"] = random.uniform(0.3, 0.7)
            tx["campaign_id"] = f"camp_acq004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- AUTH-001 to AUTH-004 --------
    def generate_auth_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["authentication"]["families"]["AUTH-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AUTH-001", random.choice(variants), "Authentication"
            )
            tx["amount"] = self._random_amount(0, 1000)
            tx["payment_rail"] = "authentication"
            tx["transaction_type"] = "login_attempt"
            tx["auth_success"] = random.random() < 0.3
            tx["authentication_method"] = "password"
            tx["is_new_device"] = True
            tx["velocity_score"] = random.uniform(0.5, 0.9)
            tx["campaign_id"] = f"camp_auth001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_auth_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["authentication"]["families"]["AUTH-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AUTH-002", random.choice(variants), "Authentication"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["authentication_method"] = "otp"
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_auth002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_auth_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["authentication"]["families"]["AUTH-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AUTH-003", random.choice(variants), "Authentication"
            )
            tx["amount"] = self._random_amount(0, 500)
            tx["payment_rail"] = "account_recovery"
            tx["transaction_type"] = random.choice(["password_reset", "account_recovery"])
            tx["auth_success"] = True
            tx["authentication_method"] = random.choice(["document_upload", "video_verification"])
            tx["is_new_device"] = True
            tx["device_age_days"] = random.randint(0, 2)
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_auth003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_auth_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["authentication"]["families"]["AUTH-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AUTH-004", random.choice(variants), "Authentication"
            )
            tx["amount"] = self._random_amount(1000, 200000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["authentication_method"] = "biometric"
            tx["is_new_beneficiary"] = random.random() < 0.5
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.1, 0.4)
            tx["campaign_id"] = f"camp_auth004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- AUT-001 to AUT-003 --------
    def generate_aut_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["authorization"]["families"]["AUT-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AUT-001", random.choice(variants), "Authorization"
            )
            tx["amount"] = self._random_amount(1000, 99999)
            tx["payment_rail"] = random.choice(["card", "bank_transfer"])
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_risk_score"] = random.uniform(0, 0.3)
            tx["velocity_score"] = random.uniform(0.3, 0.6)
            tx["campaign_id"] = f"camp_aut001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_aut_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["authorization"]["families"]["AUT-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AUT-002", random.choice(variants), "Authorization"
            )
            tx["amount"] = self._random_amount(1000, 50000)
            tx["payment_rail"] = random.choice(["card", "bank_transfer"])
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_risk_score"] = random.uniform(0, 0.2)
            tx["velocity_score"] = random.uniform(0.1, 0.3)
            tx["campaign_id"] = f"camp_aut002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_aut_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["authorization"]["families"]["AUT-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "AUT-003", random.choice(variants), "Authorization"
            )
            tx["amount"] = self._random_amount(500, 30000)
            tx["payment_rail"] = random.choice(["card", "upi", "bank_transfer"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = random.random() < 0.5
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.2, 0.5)
            tx["campaign_id"] = f"camp_aut003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- CM-001 to CM-004 --------
    def generate_cm_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["cash_out"]["families"]["CM-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "CM-001", random.choice(variants), "Cash_Out_Mule"
            )
            tx["amount"] = self._random_amount(100, 10000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi", "wallet"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.4, 0.7)
            tx["campaign_id"] = f"camp_cm001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_cm_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["cash_out"]["families"]["CM-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "CM-002", random.choice(variants), "Cash_Out_Mule"
            )
            tx["amount"] = self._random_amount(100, 5000)
            tx["payment_rail"] = "account_opening"
            tx["transaction_type"] = "account_creation"
            tx["auth_success"] = True
            tx["device_age_days"] = random.randint(0, 3)
            tx["account_age_days"] = random.randint(0, 7)
            tx["is_new_device"] = True
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_cm002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_cm_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["cash_out"]["families"]["CM-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "CM-003", random.choice(variants), "Cash_Out_Mule"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi", "crypto"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule_network")
            tx["velocity_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_cm003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_cm_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["cash_out"]["families"]["CM-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "CM-004", random.choice(variants), "Cash_Out_Mule"
            )
            tx["amount"] = self._random_amount(10000, 1000000)
            tx["payment_rail"] = "crypto"
            tx["transaction_type"] = "crypto_conversion"
            tx["auth_success"] = True
            tx["beneficiary_account_id"] = self._generate_id("crypto_wallet")
            tx["velocity_score"] = random.uniform(0.7, 0.95)
            tx["campaign_id"] = f"camp_cm004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- DFS-001 to BBE-001 --------
    def generate_dfs_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["device_session"]["families"]["DFS-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "DFS-001", random.choice(variants), "Device_Session"
            )
            tx["amount"] = self._random_amount(0, 500)
            tx["payment_rail"] = "device_session"
            tx["transaction_type"] = random.choice(["device_registration", "session_login"])
            tx["auth_success"] = True
            tx["authentication_method"] = "password"
            tx["device_age_days"] = random.randint(0, 2)
            tx["is_new_device"] = True
            tx["velocity_score"] = random.uniform(0.4, 0.7)
            tx["campaign_id"] = f"camp_dfs001_{uuid.uuid4().hex[:6]}"
            if random.random() < 0.3:
                shared_attr = uuid.uuid4().hex[:6]
                tx["device_id"] = f"dev_cluster_{shared_attr}"
            transactions.append(tx)
        return transactions
    
    def generate_eff_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["device_session"]["families"]["EFF-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "EFF-001", random.choice(variants), "Device_Session"
            )
            tx["amount"] = self._random_amount(0, 500)
            tx["payment_rail"] = "device_session"
            tx["transaction_type"] = "account_creation"
            tx["auth_success"] = True
            tx["device_age_days"] = random.randint(0, 1)
            tx["is_new_device"] = True
            tx["velocity_score"] = random.uniform(0.7, 0.95)
            tx["campaign_id"] = f"camp_eff001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_rat_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["device_session"]["families"]["RAT-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "RAT-001", random.choice(variants), "Device_Session"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["authentication_method"] = random.choice(["password", "biometric"])
            tx["device_age_days"] = random.randint(30, 365)
            tx["is_new_device"] = False
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_rat001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_bot_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["device_session"]["families"]["BOT-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "BOT-001", random.choice(variants), "Device_Session"
            )
            tx["amount"] = self._random_amount(0, 1000)
            tx["payment_rail"] = random.choice(["card", "upi"])
            tx["transaction_type"] = random.choice(["login_attempt", "auth_attempt"])
            tx["auth_success"] = random.random() < 0.3
            tx["device_age_days"] = random.randint(0, 3)
            tx["is_new_device"] = True
            tx["velocity_score"] = random.uniform(0.7, 0.95)
            tx["campaign_id"] = f"camp_bot001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_bbe_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["device_session"]["families"]["BBE-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "BBE-001", random.choice(variants), "Device_Session"
            )
            tx["amount"] = self._random_amount(1000, 100000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["authentication_method"] = "biometric"
            tx["is_new_beneficiary"] = random.random() < 0.4
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.1, 0.4)
            tx["campaign_id"] = f"camp_bbe001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- GP-001 to GP-007 --------
    def generate_gp_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["gateway_processor"]["families"]["GP-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "GP-001", random.choice(variants), "Gateway_Processor"
            )
            tx["amount"] = self._random_amount(0, 1000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("mch")
            tx["merchant_risk_score"] = random.uniform(0.3, 0.7)
            tx["campaign_id"] = f"camp_gp001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_gp_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["gateway_processor"]["families"]["GP-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "GP-002", random.choice(variants), "Gateway_Processor"
            )
            tx["amount"] = self._random_amount(0, 500)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "webhook_event"
            tx["auth_success"] = True
            tx["campaign_id"] = f"camp_gp002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_gp_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["gateway_processor"]["families"]["GP-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "GP-003", random.choice(variants), "Gateway_Processor"
            )
            tx["amount"] = self._random_amount(1, 100)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "auth_attempt"
            tx["auth_success"] = random.random() < 0.2
            tx["merchant_risk_score"] = random.uniform(0.4, 0.8)
            tx["campaign_id"] = f"camp_gp003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_gp_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["gateway_processor"]["families"]["GP-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "GP-004", random.choice(variants), "Gateway_Processor"
            )
            tx["amount"] = self._random_amount(1000, 100000)
            tx["payment_rail"] = "protocol"
            tx["transaction_type"] = "protocol_message"
            tx["auth_success"] = True
            tx["campaign_id"] = f"camp_gp004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_gp_005(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["gateway_processor"]["families"]["GP-005"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "GP-005", random.choice(variants), "Gateway_Processor"
            )
            tx["amount"] = self._random_amount(1000, 200000)
            tx["payment_rail"] = random.choice(["card", "bank_transfer"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["campaign_id"] = f"camp_gp005_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_gp_006(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["gateway_processor"]["families"]["GP-006"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "GP-006", random.choice(variants), "Gateway_Processor"
            )
            tx["amount"] = self._random_amount(1000, 300000)
            tx["payment_rail"] = "token"
            tx["transaction_type"] = "token_usage"
            tx["auth_success"] = True
            tx["campaign_id"] = f"camp_gp006_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_gp_007(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["gateway_processor"]["families"]["GP-007"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "GP-007", random.choice(variants), "Gateway_Processor"
            )
            tx["amount"] = self._random_amount(100, 10000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["velocity_score"] = random.uniform(0.8, 0.98)
            tx["campaign_id"] = f"camp_gp007_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- SIF-001 to ATO-001 (KYC) --------
    def generate_sif_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["kyc"]["families"]["SIF-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "SIF-001", random.choice(variants), "Identity_KYC"
            )
            tx["amount"] = self._random_amount(0, 1000)
            tx["payment_rail"] = "account_opening"
            tx["transaction_type"] = random.choice(["identity_verification", "document_submission"])
            tx["auth_success"] = True
            tx["authentication_method"] = "document_upload"
            tx["device_age_days"] = random.randint(0, 7)
            tx["is_new_device"] = True
            tx["merchant_risk_score"] = random.uniform(0.6, 0.95)
            tx["velocity_score"] = random.uniform(0.5, 0.9)
            tx["campaign_id"] = f"camp_sif001_{uuid.uuid4().hex[:6]}"
            if random.random() < 0.3:
                shared_attr = uuid.uuid4().hex[:6]
                tx["account_id"] = f"acc_cluster_{shared_attr}"
            transactions.append(tx)
        return transactions
    
    def generate_gdf_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["kyc"]["families"]["GDF-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "GDF-001", random.choice(variants), "Identity_KYC"
            )
            tx["amount"] = self._random_amount(0, 500)
            tx["payment_rail"] = "account_opening"
            tx["transaction_type"] = "document_submission"
            tx["auth_success"] = True
            tx["authentication_method"] = "document_upload"
            tx["device_age_days"] = random.randint(0, 3)
            tx["is_new_device"] = True
            tx["merchant_risk_score"] = random.uniform(0.7, 0.95)
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_gdf001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_dii_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["kyc"]["families"]["DII-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "DII-001", random.choice(variants), "Identity_KYC"
            )
            tx["amount"] = self._random_amount(0, 500)
            tx["payment_rail"] = "account_opening"
            tx["transaction_type"] = random.choice(["video_kyc", "biometric_verification"])
            tx["auth_success"] = True
            tx["authentication_method"] = "biometric"
            tx["device_age_days"] = random.randint(0, 5)
            tx["is_new_device"] = True
            tx["merchant_risk_score"] = random.uniform(0.8, 0.95)
            tx["velocity_score"] = random.uniform(0.7, 0.95)
            tx["campaign_id"] = f"camp_dii001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_sep_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["kyc"]["families"]["SEP-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "SEP-001", random.choice(variants), "Identity_KYC"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_sep001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_ato_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["kyc"]["families"]["ATO-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "ATO-001", random.choice(variants), "Identity_KYC"
            )
            tx["amount"] = self._random_amount(0, 1000)
            tx["payment_rail"] = "account_recovery"
            tx["transaction_type"] = random.choice(["password_reset", "account_recovery"])
            tx["auth_success"] = True
            tx["authentication_method"] = random.choice(["document_upload", "voice_verification"])
            tx["device_age_days"] = random.randint(0, 2)
            tx["is_new_device"] = True
            tx["merchant_risk_score"] = random.uniform(0.7, 0.95)
            tx["velocity_score"] = random.uniform(0.7, 0.9)
            tx["campaign_id"] = f"camp_ato001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- MCH-001 to MCH-006 --------
    def generate_mch_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["merchant"]["families"]["MCH-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "MCH-001", random.choice(variants), "Merchant"
            )
            tx["amount"] = self._random_amount(1000, 1000000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("synthetic_mch")
            tx["merchant_risk_score"] = random.uniform(0.7, 0.95)
            tx["campaign_id"] = f"camp_mch001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_mch_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["merchant"]["families"]["MCH-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "MCH-002", random.choice(variants), "Merchant"
            )
            tx["amount"] = self._random_amount(1000, 200000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("shell_mch")
            tx["merchant_risk_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_mch002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_mch_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["merchant"]["families"]["MCH-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "MCH-003", random.choice(variants), "Merchant"
            )
            tx["amount"] = self._random_amount(100, 50000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("fake_store")
            tx["merchant_risk_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_mch003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_mch_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["merchant"]["families"]["MCH-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "MCH-004", random.choice(variants), "Merchant"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("laundering_mch")
            tx["merchant_risk_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_mch004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_mch_005(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["merchant"]["families"]["MCH-005"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "MCH-005", random.choice(variants), "Merchant"
            )
            tx["amount"] = self._random_amount(100, 10000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "refund"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("mch")
            tx["merchant_risk_score"] = random.uniform(0.3, 0.7)
            tx["campaign_id"] = f"camp_mch005_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_mch_006(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["merchant"]["families"]["MCH-006"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "MCH-006", random.choice(variants), "Merchant"
            )
            tx["amount"] = self._random_amount(1000, 300000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_mch006_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- N-001 to N-004 --------
    def generate_n_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["network"]["families"]["N-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "N-001", random.choice(variants), "Cross_Stage_Network"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi", "card"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.4, 0.8)
            tx["campaign_id"] = f"camp_n001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_n_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["network"]["families"]["N-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "N-002", random.choice(variants), "Cross_Stage_Network"
            )
            tx["amount"] = self._random_amount(1000, 1000000)
            tx["payment_rail"] = random.choice(["bank_transfer", "crypto", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_n002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_n_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["network"]["families"]["N-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "N-003", random.choice(variants), "Cross_Stage_Network"
            )
            tx["amount"] = self._random_amount(1000, 2000000)
            tx["payment_rail"] = random.choice(["bank_transfer", "crypto", "card", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_n003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_n_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["network"]["families"]["N-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "N-004", random.choice(variants), "Cross_Stage_Network"
            )
            tx["amount"] = self._random_amount(10000, 1000000)
            tx["payment_rail"] = "crypto"
            tx["transaction_type"] = "crypto_transfer"
            tx["auth_success"] = True
            tx["beneficiary_account_id"] = self._generate_id("crypto_wallet")
            tx["velocity_score"] = random.uniform(0.7, 0.95)
            tx["campaign_id"] = f"camp_n004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- SIA-001 to ATO-002 (Onboarding) --------
    def generate_sia_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["onboarding"]["families"]["SIA-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "SIA-001", random.choice(variants), "Account_Creation"
            )
            tx["amount"] = self._random_amount(0, 500)
            tx["payment_rail"] = "account_opening"
            tx["transaction_type"] = random.choice(["account_creation", "identity_verification"])
            tx["auth_success"] = True
            tx["authentication_method"] = "document_upload"
            tx["device_age_days"] = random.randint(0, 3)
            tx["is_new_device"] = True
            tx["merchant_risk_score"] = random.uniform(0.6, 0.9)
            tx["velocity_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_sia001_{uuid.uuid4().hex[:6]}"
            if random.random() < 0.3:
                shared_attr = uuid.uuid4().hex[:6]
                tx["account_id"] = f"acc_farm_{shared_attr}"
            transactions.append(tx)
        return transactions
    
    def generate_mdf_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["onboarding"]["families"]["MDF-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "MDF-001", random.choice(variants), "Account_Creation"
            )
            tx["amount"] = self._random_amount(0, 1000)
            tx["payment_rail"] = "account_opening"
            tx["transaction_type"] = "document_submission"
            tx["auth_success"] = True
            tx["authentication_method"] = "document_upload"
            tx["device_age_days"] = random.randint(10, 365)
            tx["is_new_device"] = False
            tx["merchant_risk_score"] = random.uniform(0.3, 0.7)
            tx["velocity_score"] = random.uniform(0.2, 0.5)
            tx["campaign_id"] = f"camp_mdf001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_ato_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["onboarding"]["families"]["ATO-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "ATO-002", random.choice(variants), "Account_Creation"
            )
            tx["amount"] = self._random_amount(0, 1000)
            tx["payment_rail"] = "account_recovery"
            tx["transaction_type"] = random.choice(["account_recovery", "password_reset"])
            tx["auth_success"] = True
            tx["authentication_method"] = random.choice(["document_upload", "voice_verification"])
            tx["device_age_days"] = random.randint(0, 1)
            tx["is_new_device"] = True
            tx["merchant_risk_score"] = random.uniform(0.7, 0.95)
            tx["velocity_score"] = random.uniform(0.7, 0.9)
            tx["campaign_id"] = f"camp_ato002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- OB-001 to OB-006 --------
    def generate_ob_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["open_banking"]["families"]["OB-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "OB-001", random.choice(variants), "Third_Party_Open_Banking"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "consent_grant"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.4, 0.8)
            tx["campaign_id"] = f"camp_ob001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_ob_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["open_banking"]["families"]["OB-002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "OB-002", random.choice(variants), "Third_Party_Open_Banking"
            )
            tx["amount"] = self._random_amount(1000, 300000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "tpp_onboarding"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_ob002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_ob_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["open_banking"]["families"]["OB-003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "OB-003", random.choice(variants), "Third_Party_Open_Banking"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "api_access"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_ob003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_ob_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["open_banking"]["families"]["OB-004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "OB-004", random.choice(variants), "Third_Party_Open_Banking"
            )
            tx["amount"] = self._random_amount(1000, 200000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "token_usage"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.4, 0.8)
            tx["campaign_id"] = f"camp_ob004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_ob_005(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["open_banking"]["families"]["OB-005"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "OB-005", random.choice(variants), "Third_Party_Open_Banking"
            )
            tx["amount"] = self._random_amount(1000, 300000)
            tx["payment_rail"] = "bank_transfer"
            tx["transaction_type"] = "scope_access"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.3, 0.7)
            tx["campaign_id"] = f"camp_ob005_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_ob_006(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["open_banking"]["families"]["OB-006"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "OB-006", random.choice(variants), "Third_Party_Open_Banking"
            )
            tx["amount"] = self._random_amount(0, 1000)
            tx["payment_rail"] = "data_access"
            tx["transaction_type"] = "data_harvesting"
            tx["auth_success"] = True
            tx["merchant_risk_score"] = random.uniform(0, 0.3)
            tx["velocity_score"] = random.uniform(0.2, 0.5)
            tx["campaign_id"] = f"camp_ob006_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- PI-F001 to PI-F004 --------
    def generate_pi_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["payment_initiation"]["families"]["PI-F001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "PI-F001", random.choice(variants), "Payment_Initiation"
            )
            tx["amount"] = self._random_amount(1000, 500000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary")
            tx["velocity_score"] = random.uniform(0.5, 0.85)
            tx["campaign_id"] = f"camp_pi001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_pi_002(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["payment_initiation"]["families"]["PI-F002"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "PI-F002", random.choice(variants), "Payment_Initiation"
            )
            tx["amount"] = self._random_amount(1000, 1000000)
            tx["payment_rail"] = random.choice(["bank_transfer", "upi", "wallet"])
            tx["transaction_type"] = "transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("mule")
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_pi002_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_pi_003(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["payment_initiation"]["families"]["PI-F003"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "PI-F003", random.choice(variants), "Payment_Initiation"
            )
            tx["amount"] = self._random_amount(100, 10000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "refund"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("mch")
            tx["merchant_risk_score"] = random.uniform(0.3, 0.7)
            tx["campaign_id"] = f"camp_pi003_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions
    
    def generate_pi_004(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["payment_initiation"]["families"]["PI-F004"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "PI-F004", random.choice(variants), "Payment_Initiation"
            )
            tx["amount"] = self._random_amount(1000, 1000000)
            tx["payment_rail"] = "card"
            tx["transaction_type"] = "purchase"
            tx["auth_success"] = True
            tx["merchant_id"] = self._generate_id("synthetic_mch")
            tx["merchant_risk_score"] = random.uniform(0.6, 0.95)
            tx["campaign_id"] = f"camp_pi004_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions

    # -------- R-001: Payment Rail --------
    def generate_r_001(self, count: int) -> List[Dict[str, Any]]:
        transactions = []
        variants = DOCUMENT_CONFIG["payment_rail"]["families"]["R-001"]["variants"]
        for _ in range(count):
            tx = self._base_transaction()
            tx = self._set_common_fraud_attributes(
                tx, "R-001", random.choice(variants), "Payment_Rail"
            )
            tx["amount"] = self._random_amount(100000, 10000000)
            tx["payment_rail"] = "swift"
            tx["transaction_type"] = "cross_border_transfer"
            tx["auth_success"] = True
            tx["is_new_beneficiary"] = True
            tx["beneficiary_account_id"] = self._generate_id("beneficiary_bic")
            tx["velocity_score"] = random.uniform(0.6, 0.9)
            tx["campaign_id"] = f"camp_r001_{uuid.uuid4().hex[:6]}"
            transactions.append(tx)
        return transactions


# ============================================================
# DATASET GENERATOR
# ============================================================

class DatasetGenerator:
    """Main dataset generator for all 15 documents"""
    
    def __init__(self):
        self.fraud_gen = FraudGenerator()
        self.legit_gen = LegitimateGenerator()
        
        self.generation_map = {
            "agent_commerce": {
                "families": {
                    "AG-001": self.fraud_gen.generate_ag_001,
                    "AG-002": self.fraud_gen.generate_ag_002,
                    "AG-003": self.fraud_gen.generate_ag_003,
                    "AG-004": self.fraud_gen.generate_ag_004,
                    "AG-005": self.fraud_gen.generate_ag_005
                }
            },
            "aml": {
                "families": {
                    "AML-001": self.fraud_gen.generate_aml_001,
                    "AML-002": self.fraud_gen.generate_aml_002,
                    "AML-003": self.fraud_gen.generate_aml_003,
                    "AML-004": self.fraud_gen.generate_aml_004,
                    "AML-005": self.fraud_gen.generate_aml_005,
                    "AML-006": self.fraud_gen.generate_aml_006
                }
            },
            "acquirer": {
                "families": {
                    "ACQ-001": self.fraud_gen.generate_acq_001,
                    "ACQ-002": self.fraud_gen.generate_acq_002,
                    "ACQ-003": self.fraud_gen.generate_acq_003,
                    "ACQ-004": self.fraud_gen.generate_acq_004
                }
            },
            "authentication": {
                "families": {
                    "AUTH-001": self.fraud_gen.generate_auth_001,
                    "AUTH-002": self.fraud_gen.generate_auth_002,
                    "AUTH-003": self.fraud_gen.generate_auth_003,
                    "AUTH-004": self.fraud_gen.generate_auth_004
                }
            },
            "authorization": {
                "families": {
                    "AUT-001": self.fraud_gen.generate_aut_001,
                    "AUT-002": self.fraud_gen.generate_aut_002,
                    "AUT-003": self.fraud_gen.generate_aut_003
                }
            },
            "cash_out": {
                "families": {
                    "CM-001": self.fraud_gen.generate_cm_001,
                    "CM-002": self.fraud_gen.generate_cm_002,
                    "CM-003": self.fraud_gen.generate_cm_003,
                    "CM-004": self.fraud_gen.generate_cm_004
                }
            },
            "device_session": {
                "families": {
                    "DFS-001": self.fraud_gen.generate_dfs_001,
                    "EFF-001": self.fraud_gen.generate_eff_001,
                    "RAT-001": self.fraud_gen.generate_rat_001,
                    "BOT-001": self.fraud_gen.generate_bot_001,
                    "BBE-001": self.fraud_gen.generate_bbe_001
                }
            },
            "gateway_processor": {
                "families": {
                    "GP-001": self.fraud_gen.generate_gp_001,
                    "GP-002": self.fraud_gen.generate_gp_002,
                    "GP-003": self.fraud_gen.generate_gp_003,
                    "GP-004": self.fraud_gen.generate_gp_004,
                    "GP-005": self.fraud_gen.generate_gp_005,
                    "GP-006": self.fraud_gen.generate_gp_006,
                    "GP-007": self.fraud_gen.generate_gp_007
                }
            },
            "kyc": {
                "families": {
                    "SIF-001": self.fraud_gen.generate_sif_001,
                    "GDF-001": self.fraud_gen.generate_gdf_001,
                    "DII-001": self.fraud_gen.generate_dii_001,
                    "SEP-001": self.fraud_gen.generate_sep_001,
                    "ATO-001": self.fraud_gen.generate_ato_001
                }
            },
            "merchant": {
                "families": {
                    "MCH-001": self.fraud_gen.generate_mch_001,
                    "MCH-002": self.fraud_gen.generate_mch_002,
                    "MCH-003": self.fraud_gen.generate_mch_003,
                    "MCH-004": self.fraud_gen.generate_mch_004,
                    "MCH-005": self.fraud_gen.generate_mch_005,
                    "MCH-006": self.fraud_gen.generate_mch_006
                }
            },
            "network": {
                "families": {
                    "N-001": self.fraud_gen.generate_n_001,
                    "N-002": self.fraud_gen.generate_n_002,
                    "N-003": self.fraud_gen.generate_n_003,
                    "N-004": self.fraud_gen.generate_n_004
                }
            },
            "onboarding": {
                "families": {
                    "SIA-001": self.fraud_gen.generate_sia_001,
                    "MDF-001": self.fraud_gen.generate_mdf_001,
                    "ATO-002": self.fraud_gen.generate_ato_002
                }
            },
            "open_banking": {
                "families": {
                    "OB-001": self.fraud_gen.generate_ob_001,
                    "OB-002": self.fraud_gen.generate_ob_002,
                    "OB-003": self.fraud_gen.generate_ob_003,
                    "OB-004": self.fraud_gen.generate_ob_004,
                    "OB-005": self.fraud_gen.generate_ob_005,
                    "OB-006": self.fraud_gen.generate_ob_006
                }
            },
            "payment_initiation": {
                "families": {
                    "PI-F001": self.fraud_gen.generate_pi_001,
                    "PI-F002": self.fraud_gen.generate_pi_002,
                    "PI-F003": self.fraud_gen.generate_pi_003,
                    "PI-F004": self.fraud_gen.generate_pi_004
                }
            },
            "payment_rail": {
                "families": {
                    "R-001": self.fraud_gen.generate_r_001
                }
            }
        }
    
    def generate_document(self, doc_key: str) -> Dict[str, Any]:
        config = DOCUMENT_CONFIG[doc_key]
        fraud_rows = config["fraud_rows"]
        legit_rows = config["legit_rows"]
        
        print(f"\n{'='*60}")
        print(f"Generating: {doc_key}")
        print(f"  Fraud rows: {fraud_rows}")
        print(f"  Legit rows: {legit_rows}")
        print(f"  Total: {fraud_rows + legit_rows}")
        print(f"{'='*60}")
        
        legit_transactions = self.legit_gen.generate(legit_rows)
        
        fraud_transactions = []
        families = self.generation_map[doc_key]["families"]
        
        for family_id, generator_func in families.items():
            family_rows = config["families"][family_id]["rows"]
            print(f"  Generating {family_rows} fraud transactions for {family_id}...")
            fraud_transactions.extend(generator_func(family_rows))
        
        all_transactions = legit_transactions + fraud_transactions
        random.shuffle(all_transactions)
        
        print(f"  ✅ Generated {len(all_transactions)} total transactions")
        print(f"     Fraud: {len(fraud_transactions)}")
        print(f"     Legit: {len(legit_transactions)}")
        
        return {
            "document": doc_key,
            "total_rows": len(all_transactions),
            "fraud_rows": len(fraud_transactions),
            "legit_rows": len(legit_transactions),
            "transactions": all_transactions
        }
    
    def save_dataset(self, doc_key: str, data: Dict[str, Any]):
        filename = DOCUMENT_CONFIG[doc_key]["filename"]
        
        output = {
            "dataset_info": {
                "document": doc_key,
                "total_rows": data["total_rows"],
                "fraud_rows": data["fraud_rows"],
                "legit_rows": data["legit_rows"],
                "generated_at": datetime.now().isoformat(),
                "schema_version": "1.0"
            },
            "transactions": data["transactions"]
        }
        
        _write_json(filename, output)
        print(f"  💾 Saved to: {filename}")
    
    def generate_all(self):
        """Generate every document, then apply the realism layer to the COMBINED set.

        The realism pass must see all documents at once: accounts, devices and
        merchants are shared across documents, and the history features are
        computed per account in global timestamp order. Applying it per document
        would fragment each account's timeline.
        """
        print("\n" + "="*70)
        print("COMPLETE FRAUD DATASET GENERATOR")
        print(f"Generating all {len(DOCUMENT_CONFIG)} documents")
        print("="*70)

        master: List[Dict[str, Any]] = []
        for doc_key in DOCUMENT_CONFIG.keys():
            data = self.generate_document(doc_key)
            for tx in data["transactions"]:
                tx["source_document"] = doc_key
            master.extend(data["transactions"])

        # Every transaction id must be unique; the original run produced a
        # collision because ids were 8 hex chars over 107k rows.
        for i, tx in enumerate(master):
            tx["transaction_id"] = f"txn_{i:08d}_{uuid.uuid4().hex[:8]}"

        master = apply_realism(master)
        random.shuffle(master)

        # Write the per-document files back out from the realism-adjusted rows,
        # so the per-document and master files stay consistent.
        print("\n💾 Writing per-document files...")
        by_doc: Dict[str, List[Dict[str, Any]]] = {k: [] for k in DOCUMENT_CONFIG}
        for tx in master:
            by_doc[tx["source_document"]].append(tx)

        total_transactions = 0
        total_fraud = 0
        total_legit = 0
        for doc_key, rows in by_doc.items():
            fraud = sum(r["is_fraud"] for r in rows)
            self.save_dataset(doc_key, {
                "total_rows": len(rows),
                "fraud_rows": fraud,
                "legit_rows": len(rows) - fraud,
                "transactions": rows,
            })
            total_transactions += len(rows)
            total_fraud += fraud
            total_legit += len(rows) - fraud

        self.master = master

        print("\n" + "="*70)
        print("✅ GENERATION COMPLETE")
        print(f"  Total transactions: {total_transactions}")
        print(f"  Total fraud: {total_fraud}")
        print(f"  Total legit: {total_legit}")
        print("="*70)
        
        print("\n📊 SUMMARY TABLE (post-realism, so fraud/legit counts shift")
        print("   slightly from the config because of label noise)")
        print("-"*70)
        print(f"{'Document':<25} {'Total':<10} {'Fraud':<10} {'Legit':<10}")
        print("-"*70)
        for doc_key, rows in by_doc.items():
            fraud = sum(r["is_fraud"] for r in rows)
            print(f"{doc_key:<25} {len(rows):<10} {fraud:<10} {len(rows)-fraud:<10}")
        print("-"*70)
        print(f"{'TOTAL':<25} {total_transactions:<10} {total_fraud:<10} {total_legit:<10}")
        print("="*70)


# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    import argparse

    _ap = argparse.ArgumentParser(description="Generate the fraud dataset.")
    _fmt = _ap.add_mutually_exclusive_group()
    _fmt.add_argument("--compact", action="store_true",
                      help="write everything on one line (~3x smaller, unreadable)")
    _fmt.add_argument("--per-line", action="store_true",
                      help="one transaction per line: scannable without the "
                           "full indent size penalty")
    _args = _ap.parse_args()
    COMPACT_JSON = _args.compact
    ONE_TX_PER_LINE = _args.per_line

    generator = DatasetGenerator()
    generator.generate_all()

    # generate_all already produced the realism-adjusted master set; reuse it
    # rather than re-reading and re-concatenating the per-document files.
    master_dataset = generator.master

    print("\n📦 Writing master file...")
    _write_json("master_dataset.json", {
            "dataset_info": {
                "total_rows": len(master_dataset),
                "fraud_rows": sum(t["is_fraud"] for t in master_dataset),
                "generated_at": datetime.now().isoformat(),
                "schema_version": "2.0",
                "description": (
                    f"Combined dataset from all {len(DOCUMENT_CONFIG)} fraud taxonomies, "
                    "with the realism layer applied (shared entities, prior-only "
                    "history features, overlapping class distributions, evasion mix, "
                    "hard negatives, label noise)."
                ),
                "notes": (
                    "Columns prefixed meta_ and the fields attack_family, "
                    "attack_variant, lifecycle_stage, campaign_id and source_document "
                    "are label metadata. They must never be used as model features."
                ),
            },
            "transactions": master_dataset
        })

    print(f"  💾 Master dataset saved to: master_dataset.json")
    print(f"  📊 Total rows in master: {len(master_dataset)}")
    print("\n✅ ALL DONE!")