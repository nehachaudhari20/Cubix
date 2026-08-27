"""Blue Team — FraudShield ML fraud detection."""

from .fraudshield import FraudShieldModel, load_fraudshield
from .features import FeatureBuilder
from .evidence_buffer import EvidenceBuffer, DEFAULT_BUFFER_PATH
from .collector import EvidenceCollector
from .trainer import HardeningTrainer
from .evaluator import HardeningEvaluator
from .stacked_trainer import StackedEnsembleTrainer
from .stacked_model import StackedFraudShieldModel
from .anomaly import AnomalyScorer, IsolationForestTrainer, load_anomaly_scorer, combine_risk_scores
from .training_mix import (
    SPLIT_METHOD,
    build_hardening_dataset,
    build_train_val_split,
    split_adversarial_by_campaign,
    temporal_train_val_split,
)
from .evaluation_runner import EvaluationRunner
from .evaluation import (
    run_detection_suite,
    run_fidelity_checks,
    run_generalization_suite,
    run_integrity_battery,
    run_asr_evaluation,
    run_asr_for_loop,
)
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
    "StackedEnsembleTrainer",
    "StackedFraudShieldModel",
    "AnomalyScorer",
    "IsolationForestTrainer",
    "load_anomaly_scorer",
    "combine_risk_scores",
    "build_hardening_dataset",
    "build_train_val_split",
    "split_adversarial_by_campaign",
    "temporal_train_val_split",
    "SPLIT_METHOD",
    "EvaluationRunner",
    "run_detection_suite",
    "run_fidelity_checks",
    "run_generalization_suite",
    "run_integrity_battery",
    "run_asr_evaluation",
    "run_asr_for_loop",
    "DEFAULT_BUFFER_PATH",
    "evaluate_detection",
    "evaluate_detection_dict",
    "compare_detection",
    "detection_summary_table",
    "REVIEW_CAPACITY",
    "REPORT_PREVALENCES",
]
