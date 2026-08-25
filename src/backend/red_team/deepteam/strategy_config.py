"""Resolve jailbreak strategy from hypothesis + environment."""

from __future__ import annotations

import os
from typing import Optional

from backend.red_team.schemas import Hypothesis

from .schemas import JailbreakStrategy

DEFAULT_STRATEGY = "kb"


def resolve_jailbreak_strategy(hypothesis: Optional[Hypothesis] = None) -> Optional[JailbreakStrategy]:
    """Return a DeepTeam strategy, or None to use the KB campaign builder."""
    raw = (hypothesis.jailbreak_strategy if hypothesis else None) or os.environ.get(
        "RED_TEAM_JAILBREAK_STRATEGY", DEFAULT_STRATEGY
    )
    raw = (raw or DEFAULT_STRATEGY).strip().lower()
    if raw in ("kb", "linear", "default", ""):
        return None
    try:
        return JailbreakStrategy(raw)
    except ValueError:
        return None


def use_attack_engine() -> bool:
    return os.environ.get("RED_TEAM_USE_ATTACK_ENGINE", "true").lower() in ("1", "true", "yes")
