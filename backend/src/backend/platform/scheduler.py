"""Background scheduler for periodic Red↔Blue loop runs."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import get_settings
from .database import SessionLocal, init_db
from .loop_runner import LoopRunConfig, LoopRunner
from .models import SchedulerConfig

logger = logging.getLogger(__name__)


class LoopScheduler:
    """APScheduler wrapper that runs the full loop on an interval."""

    _instance: Optional["LoopScheduler"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.settings = get_settings()
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self.runner = LoopRunner()
        self._job_id = "red_blue_loop"
        self._running_loop_id: Optional[str] = None

    @classmethod
    def get(cls) -> "LoopScheduler":
        with cls._lock:
            if cls._instance is None:
                cls._instance = LoopScheduler()
            return cls._instance

    @property
    def running_loop_id(self) -> Optional[str]:
        return self._running_loop_id

    def start(self) -> None:
        init_db()
        if self.scheduler.running:
            return
        self.scheduler.start()
        config = self._load_config()
        if config.enabled:
            self._schedule(config.interval_minutes)
        logger.info("Loop scheduler started (enabled=%s)", config.enabled)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def get_config(self) -> SchedulerConfig:
        return self._load_config()

    def update_config(self, **kwargs) -> SchedulerConfig:
        session = SessionLocal()
        try:
            row = session.get(SchedulerConfig, 1)
            if row is None:
                row = SchedulerConfig(id=1)
                session.add(row)
            for key, value in kwargs.items():
                if value is not None and hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            if row.enabled:
                row.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=row.interval_minutes)
                self._schedule(row.interval_minutes)
            else:
                self._unschedule()
                row.next_run_at = None
            session.commit()
            session.refresh(row)
            return row
        finally:
            session.close()

    def _load_config(self) -> SchedulerConfig:
        session = SessionLocal()
        try:
            row = session.get(SchedulerConfig, 1)
            if row is None:
                settings = self.settings
                row = SchedulerConfig(
                    id=1,
                    enabled=settings.scheduler_enabled,
                    interval_minutes=settings.scheduler_interval_minutes,
                    families=settings.scheduler_families,
                    skip_train_v1=settings.scheduler_skip_train_v1,
                    auto_swap=settings.scheduler_auto_swap,
                    fresh_buffer=False,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            return row
        finally:
            session.close()

    def _schedule(self, interval_minutes: int) -> None:
        self._unschedule()
        self.scheduler.add_job(
            self._run_scheduled,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=self._job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def _unschedule(self) -> None:
        if self.scheduler.get_job(self._job_id):
            self.scheduler.remove_job(self._job_id)

    def _run_scheduled(self) -> None:
        if self._running_loop_id:
            logger.warning("Skipping scheduled run — loop already in progress")
            return
        config = self._load_config()
        logger.info("Starting scheduled Red↔Blue loop (families=%s)", config.families)
        self._execute(
            LoopRunConfig(
                families=config.families,
                skip_train_v1=config.skip_train_v1,
                swap_model=config.auto_swap,
                fresh_buffer=config.fresh_buffer,
                trigger="scheduler",
            )
        )

    def run_now(self, trigger: str = "manual") -> str:
        """Trigger an immediate loop run using scheduler DB config."""
        config = self._load_config()
        return self._execute(
            LoopRunConfig(
                families=config.families,
                skip_train_v1=config.skip_train_v1,
                swap_model=config.auto_swap,
                fresh_buffer=config.fresh_buffer,
                trigger=trigger,
            )
        )

    def run_with_config(self, config: LoopRunConfig) -> str:
        """Trigger a loop run with explicit parameters (API / manual)."""
        return self._execute(config)

    def _execute(self, config: LoopRunConfig) -> str:
        from uuid import uuid4

        if self._running_loop_id:
            raise RuntimeError(f"Loop already running: {self._running_loop_id}")

        run_id = config.run_id or str(uuid4())
        config.run_id = run_id
        self._running_loop_id = run_id

        def _run():
            try:
                result = self.runner.run(config)
                session = SessionLocal()
                try:
                    row = session.get(SchedulerConfig, 1)
                    if row:
                        row.last_run_id = result.run_id
                        row.next_run_at = (
                            datetime.now(timezone.utc) + timedelta(minutes=row.interval_minutes)
                            if row.enabled
                            else None
                        )
                        session.commit()
                finally:
                    session.close()
                logger.info("Loop run %s finished with status=%s", result.run_id, result.status)
            finally:
                self._running_loop_id = None

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return run_id
