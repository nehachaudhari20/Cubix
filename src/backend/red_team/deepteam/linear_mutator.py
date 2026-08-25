"""Linear jailbreak — escalate payload intensity after each sandbox block."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Optional

from backend.red_team.schemas import ActionPayload, AnalysisResult
from backend.sandbox.rules.compiled_controls import CompiledControlSet
from backend.sandbox.rules.control_compiler import ControlCompiler


class LinearMutator:
    """DeepTeam linear jailbreak: mutate blocked payments and retry."""

    ESCALATIONS = (
        ("reduce_amount", 0.75),
        ("increase_amount", 1.25),
        ("night_shift", None),
        ("new_beneficiary", None),
    )

    def __init__(self, compiled_controls: Optional[CompiledControlSet] = None):
        self.compiled = compiled_controls or ControlCompiler().compile()

    def mutate(
        self,
        payload: ActionPayload,
        analysis: AnalysisResult,
        attempt: int = 0,
    ) -> ActionPayload:
        action = copy.deepcopy(payload.action_payload)
        label = self.ESCALATIONS[attempt % len(self.ESCALATIONS)][0]
        tier1 = ControlCompiler.get_threshold_for_parameter(
            self.compiled, "PAR-AMOUNT", "amount_limit_tier1", 25000
        )

        if label == "reduce_amount":
            action["amount"] = round(float(action.get("amount", tier1)) * 0.75, 2)
        elif label == "increase_amount":
            action["amount"] = round(float(action.get("amount", tier1)) * 1.25, 2)
        elif label == "night_shift":
            action["hour"] = 2
        elif label == "new_beneficiary":
            action["beneficiary_id"] = f"BEN_LIN_{uuid.uuid4().hex[:6]}"

        self._apply_analysis_hints(action, analysis)

        return payload.model_copy(update={
            "action_payload": action,
            "narrative": f"{payload.narrative or 'payment'} [linear:{label}]",
            "variation_label": f"linear_{label}",
            "engine_validated": False,
        })

    def mutate_chain(
        self,
        payload: ActionPayload,
        analysis: AnalysisResult,
        max_attempts: int = 2,
    ) -> List[ActionPayload]:
        chain: List[ActionPayload] = []
        current = payload
        base_analysis = analysis
        for attempt in range(max_attempts):
            mutated = self.mutate(current, base_analysis, attempt=attempt)
            chain.append(mutated)
            current = mutated
        return chain

    @staticmethod
    def _apply_analysis_hints(action: Dict[str, Any], analysis: AnalysisResult) -> None:
        suggestions = " ".join(analysis.mutation_suggestions or []).lower()
        if "amount" in suggestions or "threshold" in suggestions:
            amount = float(action.get("amount", 10000))
            action["amount"] = round(amount * 0.9, 2)
        if "timing" in suggestions or "window" in suggestions or "spread" in suggestions:
            action["hour"] = 14
        if "device" in suggestions:
            action["device_id"] = f"D_RETRY_{uuid.uuid4().hex[:6]}"
        if "beneficiary" in suggestions:
            action["beneficiary_id"] = f"BEN_RETRY_{uuid.uuid4().hex[:6]}"
