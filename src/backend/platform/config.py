"""Platform settings loaded from environment."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_url: str = "sqlite:///./data/platform.db"
    api_port: int = 8000
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 60
    scheduler_families: int = 5
    scheduler_skip_train_v1: bool = True
    scheduler_auto_swap: bool = True
    evidence_buffer_path: str = "data/adversarial_buffer/evidence.jsonl"
    fraudshield_model_dir: str = "data/models"
    red_team_use_llm: bool = False


@lru_cache
def get_settings() -> PlatformSettings:
    return PlatformSettings(
        db_url=os.environ.get("DB_URL", "sqlite:///./data/platform.db"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        scheduler_enabled=os.environ.get("SCHEDULER_ENABLED", "false").lower()
        in ("1", "true", "yes"),
        scheduler_interval_minutes=int(os.environ.get("SCHEDULER_INTERVAL_MINUTES", "60")),
        scheduler_families=int(os.environ.get("SCHEDULER_FAMILIES", "5")),
        scheduler_skip_train_v1=os.environ.get("SCHEDULER_SKIP_TRAIN_V1", "true").lower()
        in ("1", "true", "yes"),
        scheduler_auto_swap=os.environ.get("SCHEDULER_AUTO_SWAP", "true").lower()
        in ("1", "true", "yes"),
        evidence_buffer_path=os.environ.get(
            "EVIDENCE_BUFFER_PATH", "data/adversarial_buffer/evidence.jsonl"
        ),
        fraudshield_model_dir=os.environ.get("FRAUDSHIELD_MODEL_DIR", "data/models"),
        red_team_use_llm=os.environ.get("RED_TEAM_USE_LLM", "false").lower()
        in ("1", "true", "yes"),
    )
