#!/usr/bin/env python3
"""Seed ~50 completed loop runs into app.db for the Mission Control dashboard."""
from __future__ import annotations

import json
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "app.db"

FAMILY_IDS = [
    "AG-001", "AG-002", "AG-003", "AG-004",
    "SIF-001", "GDF-001", "DII-001",
    "ATO-001", "ATO-002",
    "DFS-001", "EFF-001", "RAT-001", "BOT-001", "BBE-001",
    "CM-001", "CM-002", "CM-003",
    "AML-001", "AML-002", "AML-003",
    "AUTH-001", "AUT-001", "AUT-002",
    "MCH-001", "MCH-002", "MCH-003",
    "GP-001", "OB-001", "OB-002",
    "PI-001", "PI-002", "R-001", "R-002",
    "SIA-001", "MDF-001", "SEP-001",
    "N-001", "N-002", "N-003",
]

def random_families(rng: random.Random, count: int = 8) -> str:
    return ", ".join(rng.sample(FAMILY_IDS, min(count, len(FAMILY_IDS))))

def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Check existing runs
    cur.execute("SELECT COUNT(*) FROM loop_runs")
    existing = cur.fetchone()[0]
    print(f"Existing loop runs: {existing}")

    # Count how many completed runs exist
    cur.execute("SELECT COUNT(*) FROM loop_runs WHERE status='completed'")
    existing_completed = cur.fetchone()[0]
    print(f"Existing completed: {existing_completed}")

    # Target: 48 completed + 2 failed = 50 total (after existing)
    TARGET_COMPLETED = 48
    TARGET_FAILED = 2
    need_completed = max(0, TARGET_COMPLETED - existing_completed)
    need_failed = max(0, TARGET_FAILED - max(0, existing - existing_completed))
    total_to_seed = need_completed + need_failed
    print(f"Need to seed: {need_completed} completed + {need_failed} failed = {total_to_seed}")

    if total_to_seed == 0:
        print("Nothing to seed.")
        conn.close()
        return

    rng = random.Random(2024)
    now = datetime.now(timezone.utc)

    # Spread runs over the last 14 days
    start_time = now - timedelta(days=14)

    rows = []
    for i in range(total_to_seed):
        run_id = str(uuid.uuid4())
        is_failed = i < need_failed
        status = "failed" if is_failed else "completed"

        # Stagger timestamps
        offset = timedelta(hours=rng.uniform(0, 14 * 24))
        started = start_time + offset
        duration = timedelta(minutes=rng.uniform(2, 8))
        finished = started + duration

        families_count = rng.choice([4, 8, 12, 16, 24])
        families_tested = random_families(rng, families_count)
        buffer_payments = rng.randint(300, 1200)
        buffer_blocked = int(buffer_payments * rng.uniform(0.15, 0.45))
        buffer_bypassed = buffer_payments - buffer_blocked

        v1_mean = rng.uniform(0.25, 0.55)
        v2_mean = v1_mean + rng.uniform(-0.1, 0.25)
        score_lift = v2_mean - v1_mean

        if is_failed:
            error_msg = rng.choice([
                "Timeout during hardening phase",
                "Baseline model file not found",
                "LLM provider unavailable",
            ])
            val_pr_auc = None
            val_roc_auc = None
            verify_decision = None
            verify_ml_score = None
        else:
            val_pr_auc = rng.uniform(0.72, 0.95)
            val_roc_auc = rng.uniform(0.78, 0.98)
            verify_decision = rng.choice(["BLOCK", "CHALLENGE", "ALLOW"])
            verify_ml_score = rng.uniform(0.1, 0.9)
            error_msg = None

        recommend_swap = score_lift > 0

        rows.append((
            run_id,
            status,
            rng.choice(["manual", "scheduler"]),
            started.isoformat(),
            finished.isoformat() if status != "running" else None,
            families_count,
            rng.choice([True, True, True, False]),  # skip_train_v1
            rng.choice([True, False]),               # swap_model
            rng.choice([True, True, False]),         # fresh_buffer
            buffer_payments,
            buffer_bypassed,
            buffer_blocked,
            families_tested,
            v1_mean,
            v2_mean,
            score_lift,
            recommend_swap,
            val_pr_auc,
            val_roc_auc,
            verify_decision,
            verify_ml_score,
            error_msg,
        ))

    # Insert
    cur.executemany("""
        INSERT INTO loop_runs (
            id, status, trigger, started_at, finished_at,
            families_count, skip_train_v1, swap_model, fresh_buffer,
            buffer_payments, buffer_bypassed, buffer_blocked, families_tested,
            v1_buffer_mean, v2_buffer_mean, score_lift, recommend_swap,
            val_pr_auc, val_roc_auc, verify_decision, verify_ml_score,
            error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM loop_runs")
    total = cur.fetchone()[0]
    cur.execute("SELECT status, COUNT(*) FROM loop_runs GROUP BY status")
    counts = dict(cur.fetchall())
    print(f"\nSeeded {total_to_seed} runs. Total now: {total}")
    for s, c in counts.items():
        print(f"  {s}: {c}")

    conn.close()

if __name__ == "__main__":
    main()
