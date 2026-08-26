"""
Threat Hunter Agent — discovers attack hypotheses dynamically from all three KB JSON files.
"""

from typing import List, Optional

from ..schemas import Hypothesis, ThreatHunterOutput
from ..agent_helpers import OfflineKnowledge, get_llm, use_llm
from ..kb_campaign_builder import (
    build_hypothesis_from_family,
    classify_family,
    is_simulatable,
)
from ..deepteam.family_scorer import prioritize_families


class ThreatHunter:
    """Discovers novel attack hypotheses using full KB intelligence and experiment memory."""

    def __init__(self, model_name: str = None):
        self.kb = OfflineKnowledge()
        self._family_queue: List[str] = []

    def discover(
        self,
        memory_context: Optional[str] = None,
        tested_families: Optional[List[str]] = None,
    ) -> ThreatHunterOutput:
        tested = set(tested_families or [])
        llm = get_llm()
        if llm and use_llm():
            result = self._discover_with_llm(memory_context, list(tested))
            if result:
                return result
        return self._discover_from_kb(memory_context, tested)

    def hypothesis_from_family(self, family: dict) -> Hypothesis:
        """Build hypothesis directly from a KB family record."""
        return build_hypothesis_from_family(family)

    def next_untested_family(self, tested_ids: List[str]) -> Optional[dict]:
        """Return the next simulatable KB family not yet tested."""
        untested = self.kb.get_untested_families(tested_ids, limit=1)
        return untested[0] if untested else None

    def _discover_from_kb(
        self, memory_context: Optional[str], tested: set
    ) -> ThreatHunterOutput:
        simulatable = self.kb.get_simulatable_families()
        memory_lower = (memory_context or "").lower()

        candidates: List[Hypothesis] = []
        for family in simulatable:
            fid = family.get("attack_id")
            if fid in tested:
                continue

            pattern = classify_family(family)
            # Skip families recently succeeded in memory (same pattern)
            if pattern.replace("_", " ") in memory_lower and "success" in memory_lower:
                continue

            h = build_hypothesis_from_family(family)
            h.reasoning = self._enrich_reasoning(family, pattern, memory_context)
            candidates.append(h)

        if not candidates:
            # All simulatable families tested — pick highest CVSS for re-probe
            if simulatable:
                ranked = prioritize_families(
                    simulatable,
                    self.kb.signals,
                    tested_ids=tested,
                    limit=1,
                )
                if ranked:
                    family = self.kb.get_family(ranked[0].family_id) or simulatable[0]
                    candidates = [build_hypothesis_from_family(family)]
                else:
                    candidates = [build_hypothesis_from_family(simulatable[0])]
            else:
                return ThreatHunterOutput(hypotheses=[], confidence=0.0)

        ranked = prioritize_families(
            [f for f in (self.kb.get_family(h.primary_family) for h in candidates) if f],
            self.kb.signals,
            tested_ids=tested,
            limit=len(candidates),
        )
        rank_order = {item.family_id: index for index, item in enumerate(ranked)}
        candidates.sort(
            key=lambda h: rank_order.get(h.primary_family, 999),
        )

        return ThreatHunterOutput(hypotheses=candidates[:3], confidence=0.9)

    def _enrich_reasoning(self, family: dict, pattern: str, memory: Optional[str]) -> str:
        stage = family.get("lifecycle_stage", "")
        controls = (family.get("controls_targeted") or [])[:2]
        signals = (family.get("detection_signals") or [])[:2]
        signal_names = [s.get("name", "") for s in signals]
        base = (
            f"KB family {family.get('attack_id')} ({pattern}) at stage '{stage}'. "
            f"Targets controls: {', '.join(controls) or 'stage defaults'}. "
            f"Key signals: {', '.join(signal_names) or 'derived from pattern'}."
        )
        if memory and "failure" in memory.lower():
            return base + " Prior attempt failed — mutate amounts/timing."
        return base

    def _discover_with_llm(
        self, memory_context: Optional[str], tested: List[str]
    ) -> Optional[ThreatHunterOutput]:
        llm = get_llm()
        if llm is None:
            return None
        try:
            from langchain.output_parsers import PydanticOutputParser
            from backend.llm import invoke_text

            parser = PydanticOutputParser(pydantic_object=ThreatHunterOutput)
            families = self.kb.get_simulatable_families()[:20]
            family_lines = "\n".join(self.kb.format_family_summary(f) for f in families)
            stage_lines = "\n".join(
                f"- {s.get('stage_name')}: {', '.join((s.get('controls') or [])[:3])}"
                for s in self.kb.stages[:15]
            )

            prompt = f"""You are a payment fraud Threat Hunter. Propose 2-3 hypotheses from the KB.

Simulatable families ({len(families)} shown):
{family_lines}

Lifecycle stages (sample):
{stage_lines}

KB stats: {self.kb.kb_stats()}
Already tested: {tested}
Memory: {memory_context or 'None'}

{parser.get_format_instructions()}

Use ONLY real attack_id values from the family list."""

            text = invoke_text(llm, "Return only valid JSON.", prompt)
            if not text:
                return None
            return parser.parse(text)
        except Exception as exc:
            print(f"[ThreatHunter] LLM fallback: {exc}")
            return None
