"""Labs package — post-experiment analysis (control gaps, counterfactuals)."""

from .control_gap import ControlGapLab
from .failure_analysis import FailureAnalysisAggregator, run_failure_analysis_for_loop

__all__ = [
    "ControlGapLab",
    "FailureAnalysisAggregator",
    "run_failure_analysis_for_loop",
]
