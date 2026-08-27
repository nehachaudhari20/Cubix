#!/usr/bin/env python3
"""Phase 10d: Training mix builder tests."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.blue_team.schemas import EvidenceRecord
from backend.blue_team.training_mix import (
    buffer_row_priority,
    build_hardening_dataset,
    cap_hard_negatives,
    select_buffer_records,
    temporal_train_val_split,
)


def _record(
    evidence_id: str,
    *,
    decision: str = "BLOCK",
    outcome: str = "blocked",
    ml: float = 0.1,
    label: int = 1,
    campaign: str = "camp-1",
    ts: str = "2026-01-01T00:00:00Z",
    hard_negative: bool = False,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        campaign_id=campaign,
        attack_family="CM-001",
        action_type="initiate_payment",
        sandbox_decision=decision,
        evasion_outcome=outcome,
        ml_score=ml,
        label=label,
        features={"amount": 5000, "payment_rail": "upi", "hour_of_day": 12},
        timestamp=ts,
        is_hard_negative=hard_negative,
    )


def _baseline(n: int = 100) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "amount": 1000 + i,
                "payment_rail": "upi",
                "hour_of_day": 10,
                "is_fraud": i % 2,
                "source": "baseline",
                "timestamp": f"2025-06-01T{i % 24:02d}:00:00Z",
                "campaign_id": f"baseline_{i // 10}",
            }
        )
    return pd.DataFrame(rows)


def test_buffer_priority():
    bypass = _record("b1", decision="ALLOW", outcome="bypassed", ml=0.2)
    challenge = _record("c1", decision="CHALLENGE", outcome="challenged", ml=0.5)
    blocked = _record("x1", decision="BLOCK", outcome="blocked", ml=0.05)
    assert buffer_row_priority(bypass) < buffer_row_priority(challenge)
    assert buffer_row_priority(challenge) < buffer_row_priority(blocked)

    selected = select_buffer_records([blocked, challenge, bypass], max_rows=1)
    assert len(selected) == 1
    assert selected[0].evidence_id == "b1"
    print("buffer priority: OK")


def test_temporal_split_puts_buffer_in_val():
    baseline = _baseline(200)
    records = [
        _record("adv1", decision="ALLOW", outcome="bypassed", ts="2026-08-01T00:00:00Z", campaign="red-1"),
        _record("adv2", decision="BLOCK", outcome="blocked", ts="2026-08-02T00:00:00Z", campaign="red-2"),
    ]
    train_df, val_df, manifest = build_hardening_dataset(
        baseline, records, include_hard_negatives=False, val_frac=0.15
    )
    assert manifest["split_method"] == "temporal_group"
    assert len(train_df) + len(val_df) == manifest["total_rows"]
    assert manifest["val_buffer_rows"] >= 1
    val_sources = set(val_df.get("source", pd.Series(dtype=str)).tolist())
    assert "adversarial_buffer" in val_sources or manifest["val_buffer_rows"] >= 1
    print(f"temporal split: train={len(train_df)} val={len(val_df)} val_buffer={manifest['val_buffer_rows']}")


def test_hard_negative_cap():
    df = pd.DataFrame(
        {
            "is_fraud": [0] * 20 + [0] * 10 + [1] * 5,
            "source": ["baseline"] * 20 + ["hard_negative"] * 10 + ["adversarial_buffer"] * 5,
        }
    )
    capped, meta = cap_hard_negatives(df, max_ratio=0.25)
    assert meta["hard_negative_after"] <= meta["hard_negative_before"]
    assert meta["hard_negative_after"] <= 5  # 20 legit * 0.25
    print(f"hard negative cap: {meta['hard_negative_before']} -> {meta['hard_negative_after']}")


def test_manifest_fields():
    baseline = _baseline(50)
    records = [
        _record("hn1", label=0, hard_negative=True, ts="2026-08-03T00:00:00Z"),
        _record("f1", decision="ALLOW", outcome="bypassed", ts="2026-08-04T00:00:00Z"),
    ]
    _, _, manifest = build_hardening_dataset(baseline, records, include_hard_negatives=True)
    for key in (
        "baseline_rows",
        "buffer_selected_rows",
        "split_method",
        "train_rows",
        "val_rows",
        "total_rows",
    ):
        assert key in manifest, f"missing {key}"
    print("manifest fields: OK")


def test_temporal_split_empty():
    empty = pd.DataFrame(columns=["is_fraud", "source"])
    train, val, meta = temporal_train_val_split(empty)
    assert len(train) == 0 and len(val) == 0
    print("empty split: OK")


if __name__ == "__main__":
    test_buffer_priority()
    test_temporal_split_puts_buffer_in_val()
    test_hard_negative_cap()
    test_manifest_fields()
    test_temporal_split_empty()
    print("\nAll training mix tests passed.")
