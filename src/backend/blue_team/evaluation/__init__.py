"""Phase 11 evaluation sub-pillars (11a–11e)."""

from .asr import asr_summary_dict, run_asr_evaluation, run_asr_for_loop
from .context import EvaluationContext
from .detection import run_detection_suite
from .fidelity import run_fidelity_checks
from .generalization import run_generalization_suite
from .integrity import run_integrity_battery
from .manifest import load_training_manifest

__all__ = [
    "EvaluationContext",
    "load_training_manifest",
    "run_detection_suite",
    "run_fidelity_checks",
    "run_generalization_suite",
    "run_integrity_battery",
    "run_asr_evaluation",
    "run_asr_for_loop",
    "asr_summary_dict",
]
