#!/usr/bin/env python3
"""
Multi-surface-only Red → Sandbox → Blue evidence demo.

For the full product line (Threat Hunter + multi-surface + harden + eval + labs),
prefer:

  python scripts/run_full_loop.py

This script still runs evasion search (+ composites) alone against a buffer,
useful for debugging surfaces without retraining.

Usage:
  python scripts/run_multi_surface_loop.py [--families N] [--no-composites]
  python scripts/run_multi_surface_loop.py --buffer data/adversarial_buffer/evidence.jsonl
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from backend.blue_team.collector import EvidenceCollector  # noqa: E402
from backend.blue_team.evidence_buffer import EvidenceBuffer  # noqa: E402
from backend.red_team.multi_surface import run_multi_surface_phase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--families", type=int, default=0, help="limit families (0 = all)")
    parser.add_argument("--no-composites", action="store_true")
    parser.add_argument("--buffer", default="", help="evidence buffer path (default: temp)")
    args = parser.parse_args()

    os.environ.setdefault("FRAUDSHIELD_ENABLED", "false")

    buffer_path = args.buffer or os.path.join(tempfile.mkdtemp(), "evidence.jsonl")
    buffer = EvidenceBuffer(buffer_path)
    collector = EvidenceCollector(buffer=buffer)

    run_multi_surface_phase(
        collector,
        family_limit=args.families,
        include_composites=not args.no_composites,
        print_sections=True,
    )

    print()
    print("=" * 78)
    print("Blue Team evidence snapshot")
    print("=" * 78)
    stats = buffer.stats()
    print(f"adjudicated rows : {stats['adjudicated_records']}")
    print(f"bypassed/blocked : {stats['bypassed']} / {stats['blocked']}")
    print(f"families         : {len(stats['families'])}")
    print(f"rows by surface  : {stats['surfaces']}")

    try:
        from backend.blue_team.trainer import HardeningTrainer
        from backend.blue_team.training_mix import build_hardening_dataset

        baseline = HardeningTrainer().load_baseline_sample(n_legit=4000, n_fraud=4000)
        _, _, manifest = build_hardening_dataset(baseline, buffer.read_all())
        print()
        print(f"split            : {manifest['split_method']}")
        print(f"train sources    : {manifest['train_sources']}")
        print(f"val sources      : {manifest['val_sources']}")
        print(
            f"adv campaigns    : {manifest['adv_campaigns_train']} train / "
            f"{manifest['adv_campaigns_val']} val (disjoint={manifest['campaign_disjoint']})"
        )
    except FileNotFoundError as exc:
        print(f"\n[skip] training mix needs the baseline dataset: {exc}")

    print()
    print(f"evidence buffer: {buffer_path}")
    print("Tip: python scripts/run_full_loop.py  # full product loop")


if __name__ == "__main__":
    main()
