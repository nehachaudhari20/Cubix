"""
Red Team agent helpers — KB loading, LLM toggle, campaign utilities.
"""

import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from backend.knowledge.loader import KnowledgeLoader
from backend.llm import get_llm

USE_LLM = os.environ.get("RED_TEAM_USE_LLM", "false").lower() in ("1", "true", "yes")
LLM_MODEL = os.environ.get("RED_TEAM_LLM_MODEL", "gemini-2.0-flash")


def parse_llm_json(content: str, parser=None):
    """Extract and parse JSON from LLM output."""
    text = content.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    data = json.loads(text)
    if parser:
        return parser.parse(json.dumps(data))
    return data


class OfflineKnowledge:
    """Load canonical KB via KnowledgeLoader (no API required)."""

    def __init__(self):
        self.loader = KnowledgeLoader()

    @property
    def families(self) -> List[Dict]:
        return self.loader.families

    @property
    def signals(self) -> List[Dict]:
        return self.loader.signals

    @property
    def stages(self) -> List[Dict]:
        return self.loader.stages

    def get_family(self, family_id: str) -> Optional[Dict]:
        return self.loader.get_family(family_id)

    def get_families_by_stage(self, stage: str) -> List[Dict]:
        return self.loader.get_families_by_stage(stage)

    def get_stage_controls(self, stage_name: str) -> List[str]:
        from .kb_campaign_builder import get_stage_controls
        return get_stage_controls(self.stages, stage_name)

    def get_all_controls(self) -> Dict[str, List[str]]:
        return self.loader.get_all_controls()

    def get_signals_for_family(self, family_id: str) -> List[Dict]:
        """Family-embedded detection_signals plus globally matched signal records."""
        family = self.get_family(family_id)
        if not family:
            return []
        embedded = family.get("detection_signals") or []
        embedded_names = {_normalize_signal(s.get("name")) for s in embedded}
        global_matches = [
            s for s in self.signals
            if any(en in _normalize_signal(s.get("signal_name") or s.get("name")) or
                   _normalize_signal(s.get("signal_name") or s.get("name")) in en
                   for en in embedded_names if en)
        ]
        return embedded + global_matches

    def get_simulatable_families(self) -> List[Dict]:
        from .kb_campaign_builder import is_simulatable
        return [f for f in self.families if is_simulatable(f)]

    def get_untested_families(self, tested_ids: List[str], limit: int = 5) -> List[Dict]:
        tested = set(tested_ids)
        simulatable = self.get_simulatable_families()
        return [f for f in simulatable if f.get("attack_id") not in tested][:limit]

    def families_by_stage_keyword(self, keyword: str) -> List[Dict]:
        kw = keyword.lower()
        return [
            f for f in self.families
            if kw in (f.get("lifecycle_stage") or "").lower()
        ]

    def sample_families(self, n: int = 10) -> List[Dict]:
        return self.families[:n]

    def format_family_summary(self, family: Dict) -> str:
        from .kb_campaign_builder import classify_family
        return (
            f"{family.get('attack_id')}: {family.get('name')} | "
            f"Stage: {family.get('lifecycle_stage')} | "
            f"Pattern: {classify_family(family)} | "
            f"Sim: {family.get('simulation_type')} | "
            f"Variants: {', '.join((family.get('variants') or [])[:2])}"
        )

    def kb_stats(self) -> Dict[str, Any]:
        simulatable = self.get_simulatable_families()
        direct = [f for f in simulatable if f.get("sandbox_executable") is True]
        proxy = [f for f in simulatable if f.get("sandbox_executable") is False]
        return {
            "total_families": len(self.families),
            "total_signals": len(self.signals),
            "total_stages": len(self.stages),
            "simulatable_families": len(simulatable),
            "direct_executable": len(direct),
            "genai_proxy_executable": len(proxy),
            "simulatable_ids": [f.get("attack_id") for f in simulatable],
        }


def _normalize_signal(name: Optional[str]) -> str:
    return (name or "").lower().strip()


def new_campaign_ids(prefix: str = "camp") -> Dict[str, str]:
    suffix = uuid.uuid4().hex[:6]
    return {
        "campaign_id": f"{prefix}_{suffix}",
        "customer_id": f"C_{suffix}",
        "device_id": f"D_{suffix}",
        "merchant_id": f"M_{suffix}",
        "beneficiary_id": f"BEN_{suffix}",
        "account_id": f"ACC_{suffix}",
    }
