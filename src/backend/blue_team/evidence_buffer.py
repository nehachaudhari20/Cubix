"""
Adversarial evidence buffer — persists Red Team sandbox observations for Loop B.

Stores JSONL records that Blue Team uses to retrain FraudShield on attacks
that bypassed or challenged defenses.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import EvidenceRecord

DEFAULT_BUFFER_PATH = os.environ.get(
    "EVIDENCE_BUFFER_PATH",
    os.path.join("data", "adversarial_buffer", "evidence.jsonl"),
)


class EvidenceBuffer:
    """Append-only JSONL store for adversarial sandbox evidence."""

    def __init__(self, path: str = DEFAULT_BUFFER_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: EvidenceRecord) -> EvidenceRecord:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
        return record

    def read_all(self) -> List[EvidenceRecord]:
        if not self.path.exists():
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(EvidenceRecord.model_validate_json(line))
        return records

    def stats(self) -> Dict[str, Any]:
        records = self.read_all()
        if not records:
            return {
                "total": 0,
                "payment_records": 0,
                "fraud_labeled": 0,
                "bypassed": 0,
                "blocked": 0,
                "families": [],
                "path": str(self.path),
            }

        payment = [r for r in records if r.action_type == "initiate_payment"]
        bypassed = [r for r in payment if r.sandbox_decision == "ALLOW"]
        blocked = [r for r in payment if r.sandbox_decision in ("BLOCK", "CHALLENGE")]

        families = sorted({r.attack_family for r in records})
        return {
            "total": len(records),
            "payment_records": len(payment),
            "fraud_labeled": sum(1 for r in records if r.label == 1),
            "bypassed": len(bypassed),
            "blocked": len(blocked),
            "families": families,
            "path": str(self.path),
        }

    def export_training_rows(self) -> List[Dict[str, Any]]:
        """Export payment records with features + label for retraining."""
        rows = []
        for r in self.read_all():
            if r.action_type != "initiate_payment" or r.label is None:
                continue
            row = dict(r.features)
            row["is_fraud"] = r.label
            row["attack_family"] = r.attack_family
            row["campaign_id"] = r.campaign_id
            row["evidence_id"] = r.evidence_id
            row["sandbox_decision"] = r.sandbox_decision
            row["source"] = "adversarial_buffer"
            rows.append(row)
        return rows

    def clear(self):
        if self.path.exists():
            self.path.unlink()
