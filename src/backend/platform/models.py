"""ORM models for loop runs, campaign events, and scheduler config."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LoopRun(Base):
    __tablename__ = "loop_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    families_count: Mapped[int] = mapped_column(Integer, default=5)
    skip_train_v1: Mapped[bool] = mapped_column(Boolean, default=True)
    swap_model: Mapped[bool] = mapped_column(Boolean, default=True)
    fresh_buffer: Mapped[bool] = mapped_column(Boolean, default=True)
    buffer_payments: Mapped[int] = mapped_column(Integer, default=0)
    buffer_bypassed: Mapped[int] = mapped_column(Integer, default=0)
    buffer_blocked: Mapped[int] = mapped_column(Integer, default=0)
    families_tested: Mapped[str] = mapped_column(Text, default="")
    v1_buffer_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    v2_buffer_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_lift: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommend_swap: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    val_pr_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    verify_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    verify_ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class CampaignEvent(Base):
    __tablename__ = "campaign_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loop_run_id: Mapped[str] = mapped_column(String(36), index=True)
    family_id: Mapped[str] = mapped_column(String(32))
    family_name: Mapped[str] = mapped_column(String(200), default="")
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sandbox_decision: Mapped[str] = mapped_column(String(20), default="")
    evasion_outcome: Mapped[str] = mapped_column(String(20), default="")
    ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Campaign(Base):
    """One Red Team campaign: the reasoning behind an attack, not just its result."""

    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    loop_run_id: Mapped[str] = mapped_column(String(36), index=True)
    family_id: Mapped[str] = mapped_column(String(32))
    family_name: Mapped[str] = mapped_column(String(200), default="")
    lifecycle_stage: Mapped[str] = mapped_column(String(120), default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    selected_variant: Mapped[str] = mapped_column(String(200), default="")
    novelty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    success_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    hypothesis_json: Mapped[str] = mapped_column(Text, default="{}")
    plan_json: Mapped[str] = mapped_column(Text, default="{}")
    payloads_json: Mapped[str] = mapped_column(Text, default="[]")
    memory_json: Mapped[str] = mapped_column(Text, default="[]")
    steps_total: Mapped[int] = mapped_column(Integer, default=0)
    steps_bypassed: Mapped[int] = mapped_column(Integer, default=0)
    steps_blocked: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Observation(Base):
    """Full sandbox observation contract for one executed action."""

    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loop_run_id: Mapped[str] = mapped_column(String(36), index=True)
    campaign_id: Mapped[str] = mapped_column(String(64), index=True)
    family_id: Mapped[str] = mapped_column(String(32), default="")
    family_name: Mapped[str] = mapped_column(String(200), default="")
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_type: Mapped[str] = mapped_column(String(40), default="")
    target_control: Mapped[str] = mapped_column(String(200), default="")
    expected_outcome: Mapped[str] = mapped_column(String(40), default="")
    decision: Mapped[str] = mapped_column(String(20), default="")
    reason: Mapped[str] = mapped_column(String(120), default="")
    evasion_outcome: Mapped[str] = mapped_column(String(20), default="")
    blocking_control: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rule_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    payment_rail: Mapped[str] = mapped_column(String(40), default="")
    location_region: Mapped[str] = mapped_column(String(40), default="")
    control_triggers_json: Mapped[str] = mapped_column(Text, default="[]")
    journey_json: Mapped[str] = mapped_column(Text, default="[]")
    state_before_json: Mapped[str] = mapped_column(Text, default="{}")
    state_after_json: Mapped[str] = mapped_column(Text, default="{}")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    features_json: Mapped[str] = mapped_column(Text, default="{}")
    analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ModelVersion(Base):
    """FraudShield lineage: one row per trained model version."""

    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loop_run_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    version: Mapped[str] = mapped_column(String(20), default="v1")
    model_type: Mapped[str] = mapped_column(String(40), default="")
    parent_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    baseline_rows: Mapped[int] = mapped_column(Integer, default=0)
    buffer_rows: Mapped[int] = mapped_column(Integer, default=0)
    buffer_families: Mapped[str] = mapped_column(Text, default="")
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    decision_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_pr_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    buffer_mean_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_lift: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_fraud_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    report_json: Mapped[str] = mapped_column(Text, default="{}")


class SchedulerConfig(Base):
    __tablename__ = "scheduler_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    families: Mapped[int] = mapped_column(Integer, default=5)
    skip_train_v1: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_swap: Mapped[bool] = mapped_column(Boolean, default=True)
    fresh_buffer: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
