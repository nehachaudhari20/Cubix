#!/usr/bin/env python3
"""Phase 10a: shared detection metrics tests."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.blue_team.metrics import (
    best_f1_threshold,
    compare_detection,
    evaluate_detection,
    fpr_at_threshold,
    hard_negative_fpr,
    precision_at_prevalence,
    queue_precision,
    recall_at_fpr,
)


def test_recall_at_fpr():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    proba = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    r = recall_at_fpr(y, proba, 0.25)
    assert 0.0 <= r <= 1.0
    print(f"recall_at_fpr(25%): {r:.4f}")


def test_evaluate_detection():
    rng = np.random.default_rng(42)
    n = 200
    y = rng.integers(0, 2, size=n)
    proba = np.clip(y * 0.6 + rng.normal(0, 0.2, n), 0, 1)
    thr = best_f1_threshold(y, proba)
    metrics = evaluate_detection("test_model", y, proba, threshold=thr)
    assert metrics.samples == n
    assert 0.0 <= metrics.pr_auc <= 1.0
    assert 0.0 <= metrics.recall_at_1pct_fpr <= 1.0
    assert metrics.fp + metrics.tn + metrics.tp + metrics.fn == n
    print(
        f"detection: pr_auc={metrics.pr_auc:.4f} recall={metrics.recall:.4f} "
        f"fpr={metrics.fpr:.4f} recall@1%fpr={metrics.recall_at_1pct_fpr:.4f}"
    )


def test_hard_negative_fpr():
    y = np.array([0, 0, 0, 1, 1])
    proba = np.array([0.8, 0.2, 0.7, 0.9, 0.1])
    hn = np.array([True, False, True, False, False])
    stats = hard_negative_fpr(y, proba, threshold=0.5, hard_negative_mask=hn)
    assert stats["hard_negative_count"] == 2
    assert stats["hard_negative_fpr"] == 1.0
    print(f"hard_negative_fpr: {stats}")


def test_compare_detection():
    before = evaluate_detection("v1", [0, 1, 1, 0], [0.2, 0.8, 0.7, 0.3], threshold=0.5)
    after = evaluate_detection("v2", [0, 1, 1, 0], [0.1, 0.9, 0.85, 0.2], threshold=0.5)
    delta = compare_detection(before, after)
    assert "pr_auc_delta" in delta
    print(f"compare: pr_auc_delta={delta['pr_auc_delta']:.4f}")


def main() -> int:
    test_recall_at_fpr()
    test_evaluate_detection()
    test_hard_negative_fpr()
    test_compare_detection()
    print("OK: test_blue_team_metrics passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
