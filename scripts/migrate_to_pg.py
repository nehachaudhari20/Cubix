"""Migrate SQLite data to PostgreSQL."""
import sqlite3
import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
db_url = os.getenv("DB_URL")
if not db_url:
    print("ERROR: DB_URL not set")
    sys.exit(1)

print(f"Target: {db_url}")
pg_engine = create_engine(db_url)

sqlite_conn = sqlite3.connect("app.db")
sqlite_conn.row_factory = sqlite3.Row
sqlite_cur = sqlite_conn.cursor()

# Only actual boolean columns
LOOP_BOOL_COLS = {"skip_train_v1", "swap_model", "fresh_buffer", "recommend_swap"}
SCHED_BOOL_COLS = {"enabled", "skip_train_v1", "auto_swap", "fresh_buffer"}


def migrate_table(table_name, bool_cols):
    sqlite_cur.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cur.fetchall()
    if not rows:
        print(f"  {table_name}: 0 rows, skipping")
        return
    cols = [d[0] for d in sqlite_cur.description]
    print(f"Migrating {len(rows)} {table_name}...")
    with pg_engine.begin() as conn:
        for row in rows:
            data = dict(zip(cols, row))
            for k in bool_cols:
                if k in data and data[k] is not None:
                    data[k] = bool(data[k])
            placeholders = ", ".join([f":{c}" for c in data.keys()])
            col_names = ", ".join([f'"{c}"' if c == "trigger" else c for c in data.keys()])
            conn.execute(
                text(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"),
                data,
            )
    print(f"  Done.")


migrate_table("loop_runs", LOOP_BOOL_COLS)
migrate_table("campaign_events", set())
migrate_table("scheduler_config", SCHED_BOOL_COLS)

sqlite_conn.close()
print("\nMigration complete!")
