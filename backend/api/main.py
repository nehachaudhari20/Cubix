"""Unified Payment Defense Twin API — KB + Platform Command Center."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Resolve paths from the flattened root/backend layout.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

load_dotenv(ROOT / ".env")

from backend.api.routes import knowledge, platform, redteam, redteam_view  # noqa: E402
from backend.platform.database import init_db  # noqa: E402
from backend.platform.scheduler import LoopScheduler  # noqa: E402
from backend.platform.s3_storage import is_configured as s3_is_configured  # noqa: E402

FRONTEND_DIR = ROOT / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    logger = logging.getLogger("payment_defense_twin")

    # 1. Ensure persistence models are registered (imports Base.metadata tables)
    from backend.platform import persistence_models  # noqa: F401

    # 2. Create tables (SQLite or RDS)
    init_db()
    logger.info("Database initialized.")

    # 3. Log S3 status
    if s3_is_configured():
        logger.info("S3 artifact storage is ENABLED.")
    else:
        logger.info("S3 artifact storage is OFF (S3_BUCKET not set). Using local filesystem.")

    # 4. Start scheduler
    scheduler = LoopScheduler.get()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Payment Defense Twin",
    description="Red↔Blue adversarial payment laboratory — Command Center API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8000", "http://127.0.0.1:3000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge.router)
app.include_router(platform.router)
app.include_router(redteam.router)
app.include_router(redteam_view.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def dashboard():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Payment Defense Twin API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "payment-defense-twin"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=port, reload=True)
