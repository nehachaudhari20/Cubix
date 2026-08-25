"""Load training manifest / hardening metadata for evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_training_manifest(model_dir: Path, version: str) -> Dict[str, Any]:
    """Load training manifest from hardening report or features spec."""
    candidates = [
        model_dir / "hardening_report_v3.json",
        model_dir / "hardening_report.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        with open(path) as f:
            report = json.load(f)
        if report.get("version", "").startswith(version[:2]) or version in ("v2", "v3"):
            manifest = report.get("training_manifest") or report.get("mix_stats") or {}
            manifest["report_path"] = str(path)
            manifest["buffer_stats"] = report.get("buffer_stats", manifest.get("buffer_stats", {}))
            return manifest

    spec_name = f"features_{version}.json" if version != "v1" else "features.json"
    spec_path = model_dir / spec_name
    if spec_path.exists():
        with open(spec_path) as f:
            spec = json.load(f)
        return {
            "split_method": spec.get("split_method", "unknown"),
            "training_sources": spec.get("training_sources", {}),
            "report_path": str(spec_path),
        }
    return {}
