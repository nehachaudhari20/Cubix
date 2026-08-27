"""Platform settings loaded from environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    db_url: str = "sqlite:///./data/platform.db"
    db_fallback_url: str = "sqlite:///./data/platform.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 3600
    db_ssl_mode: str = "prefer"  # disable / allow / prefer / require

    # --- API ---
    api_port: int = 8000

    # --- Scheduler ---
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 60
    scheduler_families: int = 5
    scheduler_skip_train_v1: bool = True
    scheduler_auto_swap: bool = True

    # --- Evidence / Models ---
    evidence_buffer_path: str = "data/adversarial_buffer/evidence.jsonl"
    fraudshield_model_dir: str = "data/models"
    red_team_use_llm: bool = False
    llm_provider: str = "cohere"
    red_team_llm_model: str | None = None
    cohere_api_key: str | None = None

    # --- AWS ---
    aws_region: str = "us-east-1"
    aws_profile: str | None = None  # named profile, or None for IAM role
    s3_bucket: str | None = None  # required for S3 artifact storage
    s3_prefix: str = "payment-defense-twin"  # key prefix inside the bucket

    # --- RDS ---
    rds_host: str | None = None
    rds_port: int = 5432
    rds_db_name: str = "payment_defense_twin"
    rds_username: str | None = None
    rds_password: str | None = None  # static password, or "iam" to auto-generate token
    db_auth_mode: str = "password"  # "password" | "iam"


def generate_iam_auth_token(settings: "PlatformSettings") -> str:
    """Generate an RDS IAM auth token via boto3."""
    import boto3

    session_kwargs: dict = {"region_name": settings.aws_region}
    if settings.aws_profile:
        session_kwargs["profile_name"] = settings.aws_profile
    client = boto3.client("rds", **session_kwargs)
    return client.generate_db_auth_token(
        DBHostname=settings.rds_host,
        Port=settings.rds_port,
        DBUsername=settings.rds_username,
    )


def _build_rds_url(settings: "PlatformSettings") -> str | None:
    """Return a postgres URL when RDS params are set; otherwise None."""
    if not (settings.rds_host and settings.rds_username):
        return None
    password = settings.rds_password or ""
    if settings.db_auth_mode == "iam":
        password = "iam-placeholder"
    return (
        f"postgresql+psycopg://{settings.rds_username}:{password}"
        f"@{settings.rds_host}:{settings.rds_port}/{settings.rds_db_name}"
    )


def _build_db_url(settings: "PlatformSettings") -> str:
    """Prefer RDS when configured; else DB_URL / SQLite default."""
    return _build_rds_url(settings) or settings.db_url


@lru_cache
def get_settings() -> PlatformSettings:
    raw = PlatformSettings()
    # Preserve a SQLite fallback before RDS overrides db_url.
    configured = raw.db_url
    if configured.startswith("sqlite"):
        raw.db_fallback_url = configured
    else:
        raw.db_fallback_url = "sqlite:///./data/platform.db"
    raw.db_url = _build_db_url(raw)
    return raw
