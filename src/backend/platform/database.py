"""SQLAlchemy engine and session factory."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import generate_iam_auth_token, get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    is_postgres = settings.db_url.startswith("postgresql")
    is_iam = settings.db_auth_mode == "iam" and is_postgres

    connect_args: dict = {}
    pool_kwargs: dict = {}

    if is_postgres:
        # Connection pooling tuned for RDS
        pool_kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle if not is_iam else 900,  # IAM tokens expire in 15 min
            pool_pre_ping=True,  # reconnect on stale connections
        )
        # SSL mode for RDS
        ssl_mode = settings.db_ssl_mode
        if ssl_mode and ssl_mode != "disable":
            connect_args["sslmode"] = ssl_mode
        logger.info(
            "Connecting to PostgreSQL (pool_size=%s, ssl=%s, auth=%s)",
            settings.db_pool_size,
            ssl_mode,
            "iam" if is_iam else "password",
        )
    else:
        # SQLite — single-threaded
        connect_args["check_same_thread"] = False
        logger.info("Connecting to SQLite: %s", settings.db_url)

    engine = create_engine(
        settings.db_url,
        connect_args=connect_args,
        **pool_kwargs,
    )

    # --- IAM auth: inject a fresh token on every connection checkout ---
    if is_iam:
        def _inject_iam_token(dbapi_conn, connection_record):
            """Generate a fresh IAM auth token and override the password."""
            token = generate_iam_auth_token(settings)
            # psycopg2 connection password override
            dbapi_conn.password = token
            logger.debug("Refreshed IAM auth token for RDS connection.")

        event.listen(engine, "connect", _inject_iam_token)
        logger.info("IAM auth token injection registered.")

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created / verified.")


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
