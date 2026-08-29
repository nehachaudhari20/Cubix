"""
Transaction Factory — generates realistic synthetic attack transactions
covering all 57 KB families with proper risk profiles.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

RAILS = ["UPI", "Card", "PIX", "SWIFT", "RTP"]
OS_FAMILIES = ["android", "ios", "windows", "macos", "linux"]
BROWSERS = ["chrome", "safari", "firefox", "edge", "brave"]
MERCHANT_CATEGORIES = ["5411", "5812", "5999", "5399", "4812", "7995", "6011", "5967", "5732"]
COUNTRIES = ["IN", "US", "GB", "BR", "DE", "NG", "PH", "ID", "MX", "KE"]

# Risk profiles calibrated to produce realistic BLOCK/CHALLENGE/ALLOW distribution
STAGE_RISK_PROFILES = {
    "AI-Agent Commerce": {"risk_mean": 0.72, "risk_std": 0.18},
    "KYC/Identity": {"risk_mean": 0.68, "risk_std": 0.20},
    "Device/Session": {"risk_mean": 0.60, "risk_std": 0.22},
    "Authentication": {"risk_mean": 0.63, "risk_std": 0.20},
    "Payment Initiation": {"risk_mean": 0.70, "risk_std": 0.18},
    "Risk/Authorization": {"risk_mean": 0.75, "risk_std": 0.15},
    "Settlement": {"risk_mean": 0.55, "risk_std": 0.25},
}
DEFAULT_PROFILE = {"risk_mean": 0.62, "risk_std": 0.22}


@dataclass
class SyntheticTransaction:
    tx_id: str
    attack_family: str
    family_name: str
    lifecycle_stage: str
    rail: str
    amount: float
    currency: str
    country: str
    customer_id: str
    device_id: str
    merchant_id: str
    beneficiary_id: str
    account_id: str
    is_new_device: bool
    is_new_beneficiary: bool
    merchant_risk: float
    velocity_1h: int
    velocity_24h: int
    device_age_days: int
    os: str
    browser: str
    mcc: str
    risk_score: float
    ml_score: float
    rule_risk: float
    anomaly_score: float
    decision: str
    controls_triggered: List[str]
    attack_vector: str
    is_synthetic: bool = True
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.tx_id,
            "attack_family": self.attack_family,
            "family_name": self.family_name,
            "lifecycle_stage": self.lifecycle_stage,
            "rail": self.rail,
            "amount": self.amount,
            "currency": self.currency,
            "country": self.country,
            "customer_id": self.customer_id,
            "device_id": self.device_id,
            "merchant_id": self.merchant_id,
            "beneficiary_id": self.beneficiary_id,
            "account_id": self.account_id,
            "is_new_device": self.is_new_device,
            "is_new_beneficiary": self.is_new_beneficiary,
            "merchant_risk": self.merchant_risk,
            "velocity_1h": self.velocity_1h,
            "velocity_24h": self.velocity_24h,
            "device_age_days": self.device_age_days,
            "os": self.os,
            "browser": self.browser,
            "mcc": self.mcc,
            "risk_score": self.risk_score,
            "ml_score": self.ml_score,
            "rule_risk": self.rule_risk,
            "anomaly_score": self.anomaly_score,
            "decision": self.decision,
            "controls_triggered": self.controls_triggered,
            "attack_vector": self.attack_vector,
            "is_synthetic": self.is_synthetic,
            "timestamp": self.timestamp,
        }


class TransactionFactory:
    """Generates 1500+ synthetic attack transactions covering all 57 KB families."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self._load_kb()

    def _load_kb(self):
        from backend.knowledge.loader import KnowledgeLoader
        kb = KnowledgeLoader()
        self.families = kb.families
        self.family_map = {f["attack_id"]: f for f in self.families}

    def _gen_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

    def _clamp(self, v: float, lo: float = 0.01, hi: float = 0.99) -> float:
        return max(lo, min(hi, v))

    def _pick_controls(self, family: Dict[str, Any], risk: float) -> List[str]:
        targeted = family.get("controls_targeted", [])
        controls = []
        if risk > 0.7:
            controls.extend(targeted[:3])
        elif risk > 0.5:
            controls.extend(targeted[:2])
        elif risk > 0.3:
            controls.append(targeted[0] if targeted else "velocity_check")
        if self.rng.random() > 0.5:
            controls.append("new_device")
        if self.rng.random() > 0.6:
            controls.append("amount_anomaly")
        return list(set(controls))[:5]

    def generate_transaction(self, family: Dict[str, Any], index: int) -> SyntheticTransaction:
        stage = family.get("lifecycle_stage", "Payment Initiation")
        profile = STAGE_RISK_PROFILES.get(stage, DEFAULT_PROFILE)

        # Gaussian risk centered on profile mean
        risk_score = self._clamp(self.rng.gauss(profile["risk_mean"], profile["risk_std"]))

        # Component scores derived from final risk
        ml_score = self._clamp(risk_score + self.rng.gauss(0, 0.08))
        rule_risk = self._clamp(risk_score + self.rng.gauss(0, 0.10))
        anomaly = self._clamp(risk_score + self.rng.gauss(0, 0.15))

        # Decision
        if risk_score >= 0.65:
            decision = "BLOCK"
        elif risk_score >= 0.35:
            decision = "CHALLENGE"
        else:
            decision = "ALLOW"

        # Amount
        amount_ranges = {"Payment Initiation": (500, 95000), "Settlement": (10000, 500000), "AI-Agent Commerce": (100, 200000)}
        lo, hi = amount_ranges.get(stage, (200, 75000))
        amount = self.rng.uniform(lo, hi)

        velocity_1h = self.rng.randint(0, 15) if risk_score > 0.5 else self.rng.randint(0, 5)
        velocity_24h = velocity_1h + self.rng.randint(0, 30)
        controls = self._pick_controls(family, risk_score)

        variants = family.get("variants", [])
        variant = variants[index % len(variants)] if variants else f"variant-{index}"
        attack_vector = f"{family.get('attack_id', 'UNK')}/{variant}"

        base_time = datetime(2026, 8, 1, tzinfo=timezone.utc)
        ts = base_time + timedelta(hours=self.rng.randint(0, 600), minutes=self.rng.randint(0, 59))

        return SyntheticTransaction(
            tx_id=f"TX-{uuid.uuid4().hex[:12].upper()}",
            attack_family=family.get("attack_id", "UNK"),
            family_name=family.get("name", "Unknown"),
            lifecycle_stage=stage,
            rail=self.rng.choice(RAILS),
            amount=round(amount, 2),
            currency="INR" if self.rng.random() > 0.3 else "USD",
            country=self.rng.choice(COUNTRIES),
            customer_id=self._gen_id("CUST"),
            device_id=self._gen_id("DEV"),
            merchant_id=self._gen_id("MERCH"),
            beneficiary_id=self._gen_id("BEN"),
            account_id=self._gen_id("ACC"),
            is_new_device=self.rng.random() > 0.4,
            is_new_beneficiary=self.rng.random() > 0.5,
            merchant_risk=round(self.rng.uniform(0.1, 0.95), 3),
            velocity_1h=velocity_1h,
            velocity_24h=velocity_24h,
            device_age_days=self.rng.randint(0, 365),
            os=self.rng.choice(OS_FAMILIES),
            browser=self.rng.choice(BROWSERS),
            mcc=self.rng.choice(MERCHANT_CATEGORIES),
            risk_score=round(risk_score, 4),
            ml_score=round(ml_score, 4),
            rule_risk=round(rule_risk, 4),
            anomaly_score=round(anomaly, 4),
            decision=decision,
            controls_triggered=controls,
            attack_vector=attack_vector,
            timestamp=ts.isoformat(),
        )

    def generate_batch(self, target_count: int = 1500, focus_family: Optional[str] = None, focus_stage: Optional[str] = None) -> List[SyntheticTransaction]:
        transactions = []
        if focus_family:
            family = self.family_map.get(focus_family)
            if not family:
                return []
            for i in range(target_count):
                transactions.append(self.generate_transaction(family, i))
            return transactions

        families = self.families
        if focus_stage:
            stage_families = [f for f in families if f.get("lifecycle_stage") == focus_stage]
            if stage_families:
                families = stage_families

        per_family = target_count // len(families)
        remainder = target_count % len(families)
        for i, family in enumerate(families):
            count = per_family + (1 if i < remainder else 0)
            for j in range(count):
                transactions.append(self.generate_transaction(family, j))
        self.rng.shuffle(transactions)
        return transactions

    def get_summary(self, transactions: List[SyntheticTransaction]) -> Dict[str, Any]:
        if not transactions:
            return {"total": 0}
        decisions = {"BLOCK": 0, "CHALLENGE": 0, "ALLOW": 0}
        families = {}
        stages = {}
        rails = {}
        total_amount = 0.0
        risks = []
        for tx in transactions:
            decisions[tx.decision] = decisions.get(tx.decision, 0) + 1
            families[tx.attack_family] = families.get(tx.attack_family, 0) + 1
            stages[tx.lifecycle_stage] = stages.get(tx.lifecycle_stage, 0) + 1
            rails[tx.rail] = rails.get(tx.rail, 0) + 1
            total_amount += tx.amount
            risks.append(tx.risk_score)
        n = len(transactions)
        return {
            "total": n,
            "decisions": decisions,
            "attack_success_rate": round(decisions["ALLOW"] / n * 100, 1),
            "block_rate": round(decisions["BLOCK"] / n * 100, 1),
            "challenge_rate": round(decisions["CHALLENGE"] / n * 100, 1),
            "families_covered": len(families),
            "families": families,
            "stages": stages,
            "rails": rails,
            "total_amount": round(total_amount, 2),
            "avg_risk_score": round(sum(risks) / len(risks), 4),
        }
