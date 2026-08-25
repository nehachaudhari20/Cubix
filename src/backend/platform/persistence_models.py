"""
Extended ORM models for RDS persistence.

Covers campaigns, experiments, model versions, and artifact tracking
alongside the existing LoopRun / CampaignEvent / SchedulerConfig models.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Campaign — groups actions executed during a Red Team attack
# ---------------------------------------------------------------------------

class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loop_run_id: Mapped[str] = mapped_column(String(36), index=True)
    family_id: Mapped[str] = mapped_column(String(32), index=True)
    family_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | completed | failed
    entry_point: Mapped[str] = mapped_column(String(100), default="")
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    bypassed: Mapped[bool] = mapped_column(Boolean, default=False)
    ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sandbox_decision: Mapped[str] = mapped_column(String(20), default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Experiment — a single training / evaluation / hardening experiment
# ---------------------------------------------------------------------------

class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loop_run_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    experiment_type: Mapped[str] = mapped_column(String(50))  # train | evaluate | harden | unseen_eval
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | completed | failed
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob of metrics
    s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# ModelVersion — tracks each FraudShield model trained
# ---------------------------------------------------------------------------

class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_tag: Mapped[str] = mapped_column(String(50), unique=True)  # e.g. "v1", "v2", "v2026-08-25"
    status: Mapped[str] = mapped_column(String(20), default="training")  # training | active | archived | failed
    experiment_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    train_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    val_pr_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_roc_auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    training_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Artifact — generic file artifact tracking (datasets, logs, reports)
# ---------------------------------------------------------------------------

class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    artifact_type: Mapped[str] = mapped_column(String(50))  # dataset | model | evidence | report | log
    name: Mapped[str] = mapped_column(String(200))
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loop_run_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
