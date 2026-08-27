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

from .schemas import TRAINABLE_ACTION_TYPES, EvidenceRecord

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
                "surfaces": {},
                "path": str(self.path),
            }

        payment = [r for r in records if r.action_type == "initiate_payment"]
        adjudicated = [r for r in records if r.action_type in TRAINABLE_ACTION_TYPES]
        bypassed = [r for r in adjudicated if r.sandbox_decision == "ALLOW"]
        blocked = [r for r in adjudicated if r.sandbox_decision in ("BLOCK", "CHALLENGE")]

        surfaces: Dict[str, int] = {}
        for r in adjudicated:
            surfaces[r.surface] = surfaces.get(r.surface, 0) + 1

        families = sorted({r.attack_family for r in records})
        return {
            "total": len(records),
            "payment_records": len(payment),
            "adjudicated_records": len(adjudicated),
            "fraud_labeled": sum(1 for r in records if r.label == 1),
            "bypassed": len(bypassed),
            "blocked": len(blocked),
            "families": families,
            "surfaces": surfaces,
            "path": str(self.path),
        }

    def export_training_rows(self) -> List[Dict[str, Any]]:
        """Export adjudicated records (all surfaces) with features + label."""
        rows = []
        for r in self.read_all():
            if r.action_type not in TRAINABLE_ACTION_TYPES or r.label is None:
                continue
            row = dict(r.features)
            row["is_fraud"] = r.label
            row["attack_family"] = r.attack_family
            row["campaign_id"] = r.campaign_id
            row["evidence_id"] = r.evidence_id
            row["action_type"] = r.action_type
            row["surface"] = r.surface
            row["sandbox_decision"] = r.sandbox_decision
            row["evasion_outcome"] = r.evasion_outcome
            row["ml_score"] = r.ml_score
            row["is_hard_negative"] = r.is_hard_negative
            row["timestamp"] = r.timestamp
            row["source"] = "hard_negative" if r.is_hard_negative else "adversarial_buffer"
            rows.append(row)
        return rows

    def clear(self):
        if self.path.exists():
            self.path.unlink()
