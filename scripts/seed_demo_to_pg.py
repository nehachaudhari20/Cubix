"""Seed Postgres from baked demo SQLite (data/platform.db).

Safe to re-run: uses ON CONFLICT DO NOTHING.
Skips when loop_runs already has rows (unless FORCE_DEMO_SEED=1).
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = ROOT / "data" / "platform.db"

LOOP_BOOL = {"skip_train_v1", "swap_model", "fresh_buffer", "recommend_swap"}
SCHED_BOOL = {"enabled", "skip_train_v1", "auto_swap", "fresh_buffer"}


def _migrate(pg, sqlite_path: Path, table: str, bool_cols: set[str]) -> int:
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {table}")
    except sqlite3.Error as e:
        print(f"  {table}: skip ({e})")
        conn.close()
        return 0
    rows = cur.fetchall()
    if not rows:
        print(f"  {table}: 0 rows")
        conn.close()
        return 0
    cols = [d[0] for d in cur.description]
    n = 0
    with pg.begin() as c:
        for row in rows:
            data = dict(zip(cols, row))
            for k in bool_cols:
                if k in data and data[k] is not None:
                    data[k] = bool(data[k])
            col_names = ", ".join(f'"{k}"' if k == "trigger" else k for k in data)
            placeholders = ", ".join(f":{k}" for k in data)
            c.execute(
                text(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                data,
            )
            n += 1
    conn.close()
    print(f"  {table}: upserted/kept {n} rows")
    return n


def main() -> int:
    db_url = os.environ.get("DB_URL")
    if not db_url:
        print("seed_demo_to_pg: DB_URL not set — skip")
        return 0
    if db_url.startswith("sqlite"):
        print("seed_demo_to_pg: already on SQLite — skip")
        return 0

    sqlite_path = Path(os.environ.get("DEMO_SQLITE_PATH", DEFAULT_SQLITE))
    if not sqlite_path.exists():
        print(f"seed_demo_to_pg: no demo DB at {sqlite_path} — skip")
        return 0

    # Ensure tables exist before insert (uvicorn has not started yet).
    try:
        import sys

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from backend.platform.database import init_db

        init_db()
    except Exception as e:
        print(f"seed_demo_to_pg: init_db warning: {e}")

    pg = create_engine(db_url)
    force = os.environ.get("FORCE_DEMO_SEED", "").lower() in ("1", "true", "yes")
    with pg.connect() as c:
        try:
            existing = c.execute(text("SELECT COUNT(*) FROM loop_runs")).scalar() or 0
        except Exception:
            existing = 0
    if existing and not force:
        print(f"seed_demo_to_pg: loop_runs already has {existing} rows — skip")
        return 0

    print(f"seed_demo_to_pg: loading {sqlite_path} → Postgres")
    _migrate(pg, sqlite_path, "loop_runs", LOOP_BOOL)
    _migrate(pg, sqlite_path, "campaign_events", set())
    _migrate(pg, sqlite_path, "scheduler_config", SCHED_BOOL)
    print("seed_demo_to_pg: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
