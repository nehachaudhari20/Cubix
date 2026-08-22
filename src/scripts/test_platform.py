"""
Platform / Command Center tests (no full loop execution).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DB_URL", "sqlite:///./data/test_platform.db")
os.environ.setdefault("RED_TEAM_USE_LLM", "false")
os.environ.setdefault("FRAUDSHIELD_ENABLED", "true")

from fastapi.testclient import TestClient

from backend.platform.database import init_db
from backend.platform.status_service import get_system_status
from backend.platform.database import SessionLocal


def test_init_db():
    init_db()
    print("  init_db OK")


def test_system_status():
    init_db()
    session = SessionLocal()
    try:
        status = get_system_status(session)
        assert status.kb["total_families"] > 0
        assert "payment_records" in status.buffer
        assert status.model is not None
        print(f"  KB families: {status.kb['total_families']}")
        print(f"  Buffer payments: {status.buffer.get('payment_records', 0)}")
        print(f"  Model: {status.model.get('version')}")
    finally:
        session.close()
    print("  system_status OK")


def test_api_health_and_status():
    from backend.api.main import app

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    status = client.get("/api/platform/status")
    assert status.status_code == 200
    data = status.json()
    assert data["kb"]["total_families"] > 0

    kb = client.get("/api/kb/stats")
    assert kb.status_code == 200

    dashboard = client.get("/")
    assert dashboard.status_code == 200

    print("  API health + status + dashboard OK")


def test_scheduler_config():
    from backend.api.main import app

    client = TestClient(app)
    resp = client.put("/api/platform/scheduler", json={
        "enabled": False,
        "interval_minutes": 30,
        "families": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["interval_minutes"] == 30
    assert data["families"] == 3
    print("  scheduler config OK")


if __name__ == "__main__":
    print("PLATFORM / COMMAND CENTER TESTS")
    print("=" * 40)
    test_init_db()
    test_system_status()
    test_api_health_and_status()
    test_scheduler_config()
    print("=" * 40)
    print("ALL TESTS PASSED")
