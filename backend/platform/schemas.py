"""Pydantic schemas for platform API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LoopRunRequest(BaseModel):
    families: int = Field(default=8, ge=1, le=80)
    skip_train_v1: bool = True
    swap_model: bool = True
    fresh_buffer: bool = False


class CampaignEventOut(BaseModel):
    id: str
    loop_run_id: str
    family_id: str
    family_name: str
    step: Optional[int] = None
    sandbox_decision: str
    evasion_outcome: str
    ml_score: Optional[float] = None
    amount: Optional[float] = None
    created_at: datetime


class LoopRunOut(BaseModel):
    id: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    families_count: int
    skip_train_v1: bool
    swap_model: bool
    fresh_buffer: bool
    buffer_payments: int = 0
    buffer_bypassed: int = 0
    buffer_blocked: int = 0
    families_tested: str = ""
    v1_buffer_mean: Optional[float] = None
    v2_buffer_mean: Optional[float] = None
    score_lift: Optional[float] = None
    recommend_swap: Optional[bool] = None
    val_pr_auc: Optional[float] = None
    val_roc_auc: Optional[float] = None
    verify_decision: Optional[str] = None
    verify_ml_score: Optional[float] = None
    error_message: Optional[str] = None
    events: List[CampaignEventOut] = Field(default_factory=list)


class SchedulerConfigOut(BaseModel):
    enabled: bool
    interval_minutes: int
    families: int
    skip_train_v1: bool
    auto_swap: bool
    fresh_buffer: bool
    last_run_id: Optional[str] = None
    next_run_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SchedulerConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    families: Optional[int] = Field(default=None, ge=1, le=80)
    skip_train_v1: Optional[bool] = None
    auto_swap: Optional[bool] = None
    fresh_buffer: Optional[bool] = None


class SystemStatus(BaseModel):
    kb: Dict[str, Any]
    buffer: Dict[str, Any]
    model: Dict[str, Any]
    scheduler: SchedulerConfigOut
    latest_run: Optional[LoopRunOut] = None
    running_loop: Optional[str] = None
