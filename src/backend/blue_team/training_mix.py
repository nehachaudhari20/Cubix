"""
Training mix builder for Loop B hardening (Phase 10d).

- Temporal train/val split (no random shuffle leakage)
- Buffer row prioritization (bypassed > challenged > blocked)
- Hard-negative inclusion with caps
- Dataset manifest for integrity / reproducibility
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .schemas import EvidenceRecord


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes")


def _parse_timestamp(value: Any) -> pd.Timestamp:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return pd.Timestamp.min
    try:
        return pd.to_datetime(value, utc=True)
    except Exception:
        return pd.Timestamp.min


def buffer_row_priority(record: EvidenceRecord) -> Tuple[int, float]:
    """
    Lower tuple sorts first (higher priority).
    Priority: bypassed ALLOW > high ml near-threshold > challenged > blocked.
    """
    decision = (record.sandbox_decision or "").upper()
    outcome = (record.evasion_outcome or "").lower()
    ml = float(record.ml_score or 0.0)

    if decision == "ALLOW" or outcome == "bypassed":
        tier = 0
    elif decision == "CHALLENGE" or outcome == "challenged":
        tier = 1
    elif ml >= 0.35:
        tier = 2
    else:
        tier = 3
    return tier, -ml


def select_buffer_records(
    records: List[EvidenceRecord],
    *,
    max_rows: Optional[int] = None,
    prioritize_bypass: bool = True,
) -> List[EvidenceRecord]:
    """Select payment records for training with bypass/challenge priority."""
    max_rows = max_rows if max_rows is not None else _env_int("HARDEN_BUFFER_MAX_ROWS", 500)
    prioritize_bypass = prioritize_bypass and _env_bool("HARDEN_BUFFER_PRIORITIZE_BYPASS", True)

    payment = [r for r in records if r.action_type == "initiate_payment" and r.label is not None]
    if not payment:
        return []

    if prioritize_bypass:
        payment = sorted(payment, key=buffer_row_priority)

    if len(payment) <= max_rows:
        return payment

    # Ensure at least one row per family when truncating
    selected: List[EvidenceRecord] = []
    seen_families: set = set()
    for record in payment:
        if record.attack_family not in seen_families:
            selected.append(record)
            seen_families.add(record.attack_family)
        if len(selected) >= max_rows:
            break

    if len(selected) < max_rows:
        for record in payment:
            if record in selected:
                continue
            selected.append(record)
            if len(selected) >= max_rows:
                break

    return selected[:max_rows]


def records_to_dataframe(records: List[EvidenceRecord], *, source: str = "adversarial_buffer") -> pd.DataFrame:
    rows = []
    for record in records:
        row = dict(record.features)
        row["is_fraud"] = record.label if record.label is not None else 1
        row["attack_family"] = record.attack_family
        row["campaign_id"] = record.campaign_id
        row["evidence_id"] = record.evidence_id
        row["sandbox_decision"] = record.sandbox_decision
        row["evasion_outcome"] = record.evasion_outcome
        row["ml_score"] = record.ml_score
        row["is_hard_negative"] = record.is_hard_negative
        row["meta_hard_negative"] = record.is_hard_negative
        row["timestamp"] = record.timestamp
        row["source"] = "hard_negative" if record.is_hard_negative else source
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def hard_negatives_dataframe(records: List[EvidenceRecord]) -> pd.DataFrame:
    hn = [r for r in records if r.is_hard_negative and r.label == 0 and r.action_type == "initiate_payment"]
    return records_to_dataframe(hn, source="hard_negative")


def fraud_buffer_dataframe(records: List[EvidenceRecord]) -> pd.DataFrame:
    selected = select_buffer_records(records)
    fraud_only = [r for r in selected if (r.label or 1) == 1 and not r.is_hard_negative]
    return records_to_dataframe(fraud_only, source="adversarial_buffer")


def add_sort_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Add _sort_time and _sort_group for temporal splitting."""
    out = df.copy()
    if "timestamp" in out.columns:
        out["_sort_time"] = out["timestamp"].map(_parse_timestamp)
    else:
        out["_sort_time"] = pd.Timestamp.min

    if "campaign_id" in out.columns:
        groups = out["campaign_id"].astype(object)
        missing = groups.isna() | (groups.astype(str) == "nan")
        groups = groups.astype(str)
        groups.loc[missing] = "evidence_" + out.index[missing].astype(str)
        out["_sort_group"] = groups
    elif "evidence_id" in out.columns:
        out["_sort_group"] = out["evidence_id"].astype(str)
    else:
        out["_sort_group"] = "row_" + out.index.astype(str)

    source_rank = {"baseline": 0, "adversarial_buffer": 1, "hard_negative": 2}
    out["_source_rank"] = out.get("source", "baseline").map(
        lambda s: source_rank.get(str(s), 1)
    )
    return out


def temporal_train_val_split(
    df: pd.DataFrame,
    val_frac: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Chronological split: baseline history first, then buffer/hard-negative tail in val.

    Groups by campaign/evidence id; sorts by time + source rank so adversarial
    evidence from the latest Red Team run lands in validation.
    """
    if df.empty:
        return df, df, {"train_rows": 0, "val_rows": 0}

    keyed = add_sort_keys(df)
    group_order = (
        keyed.groupby("_sort_group", sort=False)
        .agg(_sort_time=("_sort_time", "min"), _source_rank=("_source_rank", "max"))
        .reset_index()
        .sort_values(["_sort_time", "_source_rank", "_sort_group"])
    )

    n_groups = len(group_order)
    n_val_groups = max(1, int(n_groups * val_frac))
    val_groups = set(group_order.tail(n_val_groups)["_sort_group"])

    train_mask = ~keyed["_sort_group"].isin(val_groups)
    train_df = keyed[train_mask].drop(columns=["_sort_time", "_sort_group", "_source_rank"], errors="ignore")
    val_df = keyed[~train_mask].drop(columns=["_sort_time", "_sort_group", "_source_rank"], errors="ignore")

    meta = {
        "split_method": "temporal_group",
        "val_frac": val_frac,
        "total_groups": n_groups,
        "val_groups": n_val_groups,
        "train_rows": len(train_df),
        "val_rows": len(val_df),
        "train_fraud_rate": float(train_df["is_fraud"].mean()) if len(train_df) else 0.0,
        "val_fraud_rate": float(val_df["is_fraud"].mean()) if len(val_df) else 0.0,
        "val_buffer_rows": int((val_df.get("source") == "adversarial_buffer").sum()) if len(val_df) else 0,
        "val_hard_negative_rows": int((val_df.get("source") == "hard_negative").sum()) if len(val_df) else 0,
        "train_sources": train_df["source"].value_counts().to_dict() if "source" in train_df else {},
        "val_sources": val_df["source"].value_counts().to_dict() if "source" in val_df else {},
    }
    return train_df.reset_index(drop=True), val_df.reset_index(drop=True), meta


def cap_hard_negatives(
    df: pd.DataFrame,
    max_ratio: Optional[float] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Limit hard negatives relative to legit baseline rows."""
    max_ratio = max_ratio if max_ratio is not None else _env_float("HARDEN_HARD_NEGATIVE_RATIO", 0.25)
    if df.empty or "source" not in df.columns:
        return df, {"hard_negative_capped": 0}

    legit = df[(df["is_fraud"] == 0) & (df["source"] != "hard_negative")]
    hn = df[df["source"] == "hard_negative"]
    other = df[(df["source"] != "hard_negative") & ~((df["is_fraud"] == 0) & (df["source"] != "hard_negative"))]

    max_hn = max(1, int(len(legit) * max_ratio)) if len(legit) else len(hn)
    if len(hn) > max_hn:
        hn = hn.sample(n=max_hn, random_state=42)

    combined = pd.concat([legit, other, hn], ignore_index=True)
    return combined, {
        "hard_negative_before": int((df["source"] == "hard_negative").sum()),
        "hard_negative_after": len(hn),
        "hard_negative_max_ratio": max_ratio,
    }


def build_hardening_dataset(
    baseline_df: pd.DataFrame,
    buffer_records: List[EvidenceRecord],
    *,
    include_hard_negatives: bool = True,
    val_frac: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Assemble train/val frames with temporal split and mix manifest."""
    parts = [baseline_df.copy()]
    buffer_df = fraud_buffer_dataframe(buffer_records)
    if not buffer_df.empty:
        parts.append(buffer_df)

    hn_stats: Dict[str, Any] = {"hard_negative_rows": 0}
    if include_hard_negatives:
        hn_df = hard_negatives_dataframe(buffer_records)
        if not hn_df.empty:
            parts.append(hn_df)
            hn_stats["hard_negative_rows"] = len(hn_df)

    combined = pd.concat(parts, ignore_index=True)
    combined, cap_meta = cap_hard_negatives(combined)
    train_df, val_df, split_meta = temporal_train_val_split(combined, val_frac=val_frac)

    bypassed = sum(
        1 for r in buffer_records
        if r.action_type == "initiate_payment"
        and (r.sandbox_decision == "ALLOW" or r.evasion_outcome == "bypassed")
    )

    manifest = {
        "baseline_rows": len(baseline_df),
        "buffer_selected_rows": len(buffer_df),
        "buffer_total_payment": sum(
            1 for r in buffer_records if r.action_type == "initiate_payment"
        ),
        "buffer_bypassed_available": bypassed,
        **hn_stats,
        **cap_meta,
        **split_meta,
        "total_rows": len(combined),
        "fraud_rows": int((combined["is_fraud"] == 1).sum()),
        "legit_rows": int((combined["is_fraud"] == 0).sum()),
    }
    return train_df, val_df, manifest
