"""Blue Team data contracts."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Sandbox actions that adjudicate a control surface and therefore produce a
# trainable row. Setup actions (register_customer, register_device, ...) only
# mutate world state and are skipped by the evidence collector.
#
# Sourced from the shared taxonomy so techniques and surface-entry actions stay in
# one place: `backend/taxonomy/techniques.py`. Adding a technique there makes it
# trainable here with no change to this module.
from backend.taxonomy import all_action_types as _all_action_types  # noqa: E402
from backend.taxonomy import surface_for_action as _surface_for_action  # noqa: E402

TRAINABLE_ACTION_TYPES = _all_action_types()


def action_surface(action_type: str) -> str:
    """Surface that adjudicated an action; defaults to payment for legacy rows."""
    return _surface_for_action(action_type) or "payment"


# Backwards-compatible mapping view for callers that indexed a dict.
ACTION_SURFACE = {action: action_surface(action) for action in TRAINABLE_ACTION_TYPES}


class FraudShieldPrediction(BaseModel):
    """ML fraud score for one transaction."""
    fraud_probability: float = Field(ge=0, le=1)
    decision_threshold: float = Field(default=0.5)
    is_fraud_predicted: bool = False
    model_version: str = "v1"
    features_used: List[str] = Field(default_factory=list)
    missing_features: List[str] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    """One sandbox observation stored for Loop B hardening."""
    evidence_id: str
    campaign_id: str
    attack_family: str
    action_type: str
    surface: str = "payment"  # payment | agent | auth_se | kyc | open_banking
    scenario_type: Optional[str] = None  # KB entry point / template pattern
    sandbox_decision: str
    evasion_outcome: str = "unknown"  # bypassed | challenged | blocked
    analysis_outcome: Optional[str] = None
    blocking_control: Optional[str] = None
    attack_variant: Optional[str] = None
    control_triggers: List[str] = Field(default_factory=list)
    ml_score: Optional[float] = None
    rule_risk: Optional[float] = None
    risk_score: Optional[float] = None
    label: Optional[int] = None  # 1=fraud attempt, 0=legit
    features: Dict[str, Any] = Field(default_factory=dict)
    amount: Optional[float] = None
    step: Optional[int] = None
    source: str = "red_team"
    timestamp: str
    is_hard_negative: bool = False
    legitimacy_reason: Optional[str] = None


class HardeningReport(BaseModel):
    """Before/after comparison for Loop B hardening."""
    v1_version: str = "v1"
    v2_version: str = "v2"
    buffer_records: int = 0
    v1_buffer_mean_score: float = 0.0
    v2_buffer_mean_score: float = 0.0
    buffer_score_lift: float = 0.0
    v1_baseline_fraud_recall: float = 0.0
    v2_baseline_fraud_recall: float = 0.0
    bypassed_attacks: int = 0
    recommend_swap: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class DetectionMetrics(BaseModel):
    """Detection pillar metrics (Phase 10a evaluation framework)."""
    model: str = "unknown"
    samples: int = 0
    fraud_rate: float = 0.0
    pr_auc: float = 0.0
    roc_auc: float = 0.0
    f1: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    fpr: float = 0.0
    recall_at_1pct_fpr: float = 0.0
    recall_at_0p1pct_fpr: float = 0.0
    queue_precision_top1pct: float = 0.0
    brier: float = 0.0
    threshold: float = 0.5
    tn: int = 0
    fp: int = 0
    fn: int = 0
    tp: int = 0
    review_queue_size: int = 0


class FidelityMetrics(BaseModel):
    """Fidelity pillar — score behavior vs legitimate transaction patterns (11b)."""
    legit_mean_score: float = 0.0
    legit_std_score: float = 0.0
    fraud_mean_score: float = 0.0
    score_separation: float = 0.0
    amount_score_correlation: float = 0.0
    amount_ks_stat: float = 0.0
    amount_buckets: List[Dict[str, Any]] = Field(default_factory=list)
    hour_score_std: float = 0.0
    hour_profile: Dict[str, float] = Field(default_factory=dict)
    day_of_week_spread: float = 0.0
    timing_ks_stat: float = 0.0
    rail_score_spread: float = 0.0
    velocity_correlation: float = 0.0
    legit_samples: int = 0
    fraud_samples: int = 0
    checks: List["DistributionCheck"] = Field(default_factory=list)
    all_checks_passed: bool = False


class DistributionCheck(BaseModel):
    name: str
    passed: bool
    value: float = 0.0
    threshold: float = 0.0
    detail: str = ""


class DetectionSuiteResult(BaseModel):
    """Phase 11a — detection on holdout, test, and buffer slices."""
    holdout: Dict[str, Any] = Field(default_factory=dict)
    test: Dict[str, Any] = Field(default_factory=dict)
    buffer: Dict[str, Any] = Field(default_factory=dict)
    suite_table: List[Dict[str, Any]] = Field(default_factory=list)
    summary_table: Dict[str, Any] = Field(default_factory=dict)
    primary_metric: str = "pr_auc"
    before_holdout_pr_auc: float = 0.0
    after_holdout_pr_auc: float = 0.0
    buffer_recall_lift: float = 0.0


class FamilyRecall(BaseModel):
    family: str = ""
    samples: int = 0
    recall: float = 0.0
    mean_score: float = 0.0


class LOFOMetrics(BaseModel):
    held_out_family: str = ""
    held_out_samples: int = 0
    held_out_recall: float = 0.0
    train_proxy_samples: int = 0
    train_proxy_recall: float = 0.0
    recall_gap: float = 0.0


class VariantRecall(BaseModel):
    variant: str = ""
    samples: int = 0
    recall: float = 0.0
    mean_score: float = 0.0
    is_unseen: bool = False


class CompositeCampaignMetrics(BaseModel):
    campaign_id: str = ""
    steps: int = 0
    families: List[str] = Field(default_factory=list)
    is_composite: bool = False
    recall: float = 0.0
    mean_score: float = 0.0
    bypass_rate: float = 0.0


class GeneralizationMetrics(BaseModel):
    """Generalization pillar — LOFO, unseen family/variant, composite (11c)."""
    buffer_families: List[str] = Field(default_factory=list)
    trained_families: List[str] = Field(default_factory=list)
    family_recall: List[FamilyRecall] = Field(default_factory=list)
    mean_family_recall: float = 0.0
    min_family_recall: float = 0.0
    unseen_family_count: int = 0
    unseen_family_recall: float = 0.0
    seen_family_recall: float = 0.0
    lofo: List[LOFOMetrics] = Field(default_factory=list)
    mean_lofo_gap: float = 0.0
    variant_recall: List[VariantRecall] = Field(default_factory=list)
    unseen_variant_count: int = 0
    unseen_variant_recall: float = 0.0
    composite_campaigns: List[CompositeCampaignMetrics] = Field(default_factory=list)
    composite_campaign_count: int = 0
    composite_mean_recall: float = 0.0


class IntegrityCheck(BaseModel):
    name: str
    passed: bool
    value: float = 0.0
    threshold: float = 0.0
    detail: str = ""


class IntegrityMetrics(BaseModel):
    """Integrity pillar — leakage, null control, ablation, hard negatives, temporal split."""
    checks: List[IntegrityCheck] = Field(default_factory=list)
    passed_count: int = 0
    total_checks: int = 0
    all_passed: bool = False
    hard_negative_fpr: float = 0.0
    hard_negative_count: int = 0
    split_method: str = "unknown"
    val_buffer_rows: int = 0
    training_manifest: Dict[str, Any] = Field(default_factory=dict)


class FamilyASR(BaseModel):
    family: str = ""
    attacks: int = 0
    historical_bypass_rate: float = 0.0
    before_ml_recall: float = 0.0
    after_ml_recall: float = 0.0
    asr_reduction: float = 0.0


class SurfaceASR(BaseModel):
    """ASR broken out per sandbox control surface (payment, agent, kyc, ...)."""
    surface: str = ""
    attacks: int = 0
    historical_bypass_rate: float = 0.0
    before_ml_recall: float = 0.0
    after_ml_recall: float = 0.0
    asr_reduction: float = 0.0


class ASRMetrics(BaseModel):
    """
    Attack Success Rate — sandbox bypass before vs ML catch after (11e).

    Reported at two operating points:
      - native:  each model at its own decision threshold (deployment view)
      - matched: both models at the threshold giving the same baseline FPR
                 (apples-to-apples view; a model is not "worse" merely because
                 its threshold was calibrated more conservatively)
    """
    payment_attacks: int = 0
    historical_bypass_count: int = 0
    historical_bypass_rate: float = 0.0
    historical_block_rate: float = 0.0
    before_ml_recall: float = 0.0
    after_ml_recall: float = 0.0
    ml_recall_lift: float = 0.0
    before_ml_asr: float = 0.0
    after_ml_asr: float = 0.0
    projected_bypass_rate_after: float = 0.0
    asr_reduction: float = 0.0

    # Matched operating point (equal baseline FPR for both models)
    matched_fpr: Optional[float] = None
    before_threshold_matched: Optional[float] = None
    after_threshold_matched: Optional[float] = None
    before_ml_recall_matched: float = 0.0
    after_ml_recall_matched: float = 0.0
    ml_recall_lift_matched: float = 0.0
    before_ml_asr_matched: float = 0.0
    after_ml_asr_matched: float = 0.0
    asr_reduction_matched: float = 0.0

    per_family: List[FamilyASR] = Field(default_factory=list)
    per_surface: List[SurfaceASR] = Field(default_factory=list)


class GraphFidelityMetrics(BaseModel):
    """Graph signal fidelity on adversarial buffer (Phase 13)."""
    buffer_samples: int = 0
    graph_signal_stats: Dict[str, Any] = Field(default_factory=dict)
    graph_heavy_count: int = 0
    graph_heavy_coverage: float = 0.0
    graph_heavy_recall: float = 0.0
    graph_light_recall: float = 0.0
    checks: List[Dict[str, Any]] = Field(default_factory=list)
    all_checks_passed: bool = False


class GraphModelMetrics(BaseModel):
    """Graph model evaluation — clusters, composite, ablation (Phase 14)."""
    buffer_samples: int = 0
    clusters_detected: int = 0
    clusters: List[Dict[str, Any]] = Field(default_factory=list)
    composite_cross_account_count: int = 0
    composite_campaigns: List[Dict[str, Any]] = Field(default_factory=list)
    tabular_before_recall: float = 0.0
    tabular_after_recall: float = 0.0
    graph_before_recall: float = 0.0
    graph_after_recall: float = 0.0
    graph_recall_lift: float = 0.0
    tabular_before_asr: float = 0.0
    tabular_after_asr: float = 0.0
    graph_before_asr: float = 0.0
    graph_after_asr: float = 0.0
    graph_asr_reduction: float = 0.0
    graph_heavy_tabular_recall: float = 0.0
    graph_heavy_graph_recall: float = 0.0
    graph_heavy_recall_lift: float = 0.0


class EvaluationReport(BaseModel):
    """Full Phase 11–14 evaluation report."""
    before_version: str = "v1"
    after_version: str = "v2"
    generated_at: str = ""
    detection: DetectionSuiteResult = Field(default_factory=DetectionSuiteResult)
    fidelity: FidelityMetrics = Field(default_factory=FidelityMetrics)
    generalization: GeneralizationMetrics = Field(default_factory=GeneralizationMetrics)
    integrity: IntegrityMetrics = Field(default_factory=IntegrityMetrics)
    asr: ASRMetrics = Field(default_factory=ASRMetrics)
    graph_fidelity: GraphFidelityMetrics = Field(default_factory=GraphFidelityMetrics)
    graph_model: GraphModelMetrics = Field(default_factory=GraphModelMetrics)
    failure_analysis: Optional[Dict[str, Any]] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
