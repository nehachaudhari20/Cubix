"""SQLAlchemy engine and session factory.

Prefers RDS/PostgreSQL when configured, probes connectivity, and falls back to
SQLite if RDS is unreachable so local CLI/API runs still work offline.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import generate_iam_auth_token, get_settings

logger = logging.getLogger(__name__)

DEFAULT_SQLITE_URL = "sqlite:///./data/platform.db"


class Base(DeclarativeBase):
    pass


def _create_engine_for_url(db_url: str, settings, *, is_iam: bool = False) -> Engine:
    is_postgres = db_url.startswith("postgresql")
    connect_args: dict = {}
    pool_kwargs: dict = {}

    if is_postgres:
        pool_kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle if not is_iam else 900,
            pool_pre_ping=True,
        )
        connect_args["connect_timeout"] = int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))
        ssl_mode = settings.db_ssl_mode
        if ssl_mode and ssl_mode != "disable":
            connect_args["sslmode"] = ssl_mode
        logger.info(
            "Connecting to PostgreSQL (pool_size=%s, ssl=%s, auth=%s, timeout=%ss)",
            settings.db_pool_size,
            ssl_mode,
            "iam" if is_iam else "password",
            connect_args["connect_timeout"],
        )
    else:
        connect_args["check_same_thread"] = False
        # Ensure parent dir exists for file-backed SQLite
        if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
            path = db_url.replace("sqlite:///", "", 1)
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        logger.info("Connecting to SQLite: %s", db_url)

    engine = create_engine(db_url, connect_args=connect_args, **pool_kwargs)

    if is_iam and is_postgres:
        def _inject_iam_token(dbapi_conn, connection_record):
            token = generate_iam_auth_token(settings)
            dbapi_conn.password = token
            logger.debug("Refreshed IAM auth token for RDS connection.")

        event.listen(engine, "connect", _inject_iam_token)
        logger.info("IAM auth token injection registered.")

    return engine


def _probe(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database probe failed: %s", exc)
        return False


def _make_engine() -> Engine:
    settings = get_settings()
    preferred = settings.db_url
    is_iam = settings.db_auth_mode == "iam" and preferred.startswith("postgresql")

    engine = _create_engine_for_url(preferred, settings, is_iam=is_iam)

    if not preferred.startswith("postgresql"):
        return engine

    if _probe(engine):
        print(f"  Database: RDS/PostgreSQL OK ({settings.rds_host})")
        logger.info("Using RDS/PostgreSQL at %s", settings.rds_host)
        return engine

    fallback = getattr(settings, "db_fallback_url", None) or DEFAULT_SQLITE_URL
    msg = (
        f"RDS unreachable ({settings.rds_host}); falling back to SQLite ({fallback})"
    )
    print(f"  Database: {msg}")
    logger.warning(msg)

    try:
        engine.dispose()
    except Exception:
        pass

    settings.db_url = fallback
    return _create_engine_for_url(fallback, settings, is_iam=False)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created / verified (%s)", get_settings().db_url)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
