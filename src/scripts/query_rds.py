"""
Query RDS PostgreSQL using credentials from .env.

Examples:
  python src/scripts/query_rds.py
  python src/scripts/query_rds.py --tables
  python src/scripts/query_rds.py --table loop_runs --limit 5
  python src/scripts/query_rds.py --sql "SELECT COUNT(*) FROM campaign_events"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.chdir(ROOT)
load_dotenv(ROOT / ".env")

from backend.platform.config import generate_iam_auth_token, get_settings  # noqa: E402

APP_TABLES = (
    "loop_runs",
    "campaign_events",
    "scheduler_config",
    "campaigns",
    "experiments",
    "model_versions",
    "artifacts",
)


def connect():
    settings = get_settings()
    if not settings.rds_host or not settings.rds_username:
        raise SystemExit("RDS is not configured. Set RDS_HOST and RDS_USERNAME in .env")

    password = settings.rds_password or ""
    if settings.db_auth_mode == "iam":
        password = generate_iam_auth_token(settings)

    conn = psycopg2.connect(
        host=settings.rds_host,
        port=settings.rds_port,
        database=settings.rds_db_name,
        user=settings.rds_username,
        password=password,
        sslmode=settings.db_ssl_mode,
        connect_timeout=15,
    )
    return conn, settings


def print_rows(title: str, rows: list[dict]) -> None:
    print(f"\n=== {title} ===")
    if not rows:
        print("(no rows)")
        return

    columns = list(rows[0].keys())
    widths = {
        col: max(len(col), *(len(str(row.get(col, ""))) for row in rows))
        for col in columns
    }

    header = " | ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("-+-".join("-" * widths[col] for col in columns))
    for row in rows:
        print(" | ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


def fetch_all(conn, sql: str, params: tuple | None = None) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        try:
            return [dict(row) for row in cur.fetchall()]
        except psycopg2.ProgrammingError:
            conn.commit()
            return []


def show_connection_info(conn, settings) -> None:
    version = fetch_all(conn, "SELECT version() AS version")[0]["version"]
    db_name = fetch_all(conn, "SELECT current_database() AS db")[0]["db"]
    print("Connected to RDS")
    print(f"  Host:     {settings.rds_host}")
    print(f"  Database: {db_name}")
    print(f"  User:     {settings.rds_username}")
    print(f"  Auth:     {settings.db_auth_mode}")
    print(f"  Version:  {version}")


def show_tables(conn) -> None:
    rows = fetch_all(
        conn,
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
        """,
    )
    print_rows("Tables", rows)


def show_row_counts(conn) -> None:
    parts = [
        f"SELECT '{table}' AS table_name, COUNT(*)::bigint AS row_count FROM {table}"
        for table in APP_TABLES
    ]
    sql = "\nUNION ALL\n".join(parts) + "\nORDER BY table_name"
    print_rows("Row counts", fetch_all(conn, sql))


def show_scheduler(conn) -> None:
    print_rows("Scheduler config", fetch_all(conn, "SELECT * FROM scheduler_config WHERE id = 1"))


def show_recent_runs(conn, limit: int) -> None:
    print_rows(
        "Recent loop runs",
        fetch_all(
            conn,
            """
            SELECT id, status, trigger, started_at, finished_at, families_count
            FROM loop_runs
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limit,),
        ),
    )


def show_recent_events(conn, limit: int) -> None:
    print_rows(
        "Recent campaign events",
        fetch_all(
            conn,
            """
            SELECT id, loop_run_id, family_name, sandbox_decision, evasion_outcome, created_at
            FROM campaign_events
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ),
    )


def show_table_preview(conn, table: str, limit: int) -> None:
    if table not in APP_TABLES and not table.replace("_", "").isalnum():
        raise SystemExit(f"Unsupported table name: {table}")

    exists = fetch_all(
        conn,
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    if not exists:
        raise SystemExit(f"Table not found: {table}")

    print_rows(
        f"{table} (latest {limit})",
        fetch_all(conn, f"SELECT * FROM {table} LIMIT %s", (limit,)),
    )


def run_custom_sql(conn, sql: str) -> None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql)
        if cur.description is None:
            conn.commit()
            print(f"\nOK ({cur.rowcount} rows affected)")
            return
        rows = [dict(row) for row in cur.fetchall()]
    print_rows("Query result", rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query Payment Defense Twin RDS database")
    parser.add_argument("--tables", action="store_true", help="List tables only")
    parser.add_argument("--table", help="Preview rows from one table")
    parser.add_argument("--sql", help="Run a custom SQL query")
    parser.add_argument("--limit", type=int, default=10, help="Row limit for previews")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    conn, settings = connect()

    try:
        show_connection_info(conn, settings)

        if args.sql:
            run_custom_sql(conn, args.sql)
            return

        if args.tables:
            show_tables(conn)
            return

        if args.table:
            show_table_preview(conn, args.table, args.limit)
            return

        show_tables(conn)
        show_row_counts(conn)
        show_scheduler(conn)
        show_recent_runs(conn, args.limit)
        show_recent_events(conn, args.limit)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
