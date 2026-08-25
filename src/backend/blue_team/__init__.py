"""Blue Team — FraudShield ML fraud detection."""

from .fraudshield import FraudShieldModel, load_fraudshield
from .features import FeatureBuilder
from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH
from .collector import EvidenceCollector
from .trainer import HardeningTrainer
from .evaluator import HardeningEvaluator
from .metrics import (
    REVIEW_CAPACITY,
    REPORT_PREVALENCES,
    evaluate_detection,
    evaluate_detection_dict,
    compare_detection,
    detection_summary_table,
)

__all__ = [
    "FraudShieldModel",
    "load_fraudshield",
    "FeatureBuilder",
    "EvidenceBuffer",
    "EvidenceCollector",
    "HardeningTrainer",
    "HardeningEvaluator",
    "DEFAULT_BUFFER_PATH",
    "evaluate_detection",
    "evaluate_detection_dict",
    "compare_detection",
    "detection_summary_table",
    "REVIEW_CAPACITY",
    "REPORT_PREVALENCES",
]
