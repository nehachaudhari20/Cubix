"""Unified Payment Defense Twin API — KB + Platform Command Center."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Ensure project root and src are on path
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.chdir(ROOT)

load_dotenv(ROOT / ".env")

from backend.api.routes import knowledge, platform  # noqa: E402
from backend.platform.database import init_db  # noqa: E402
from backend.platform.scheduler import LoopScheduler  # noqa: E402

FRONTEND_DIR = ROOT / "src" / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

app.include_router(knowledge.router)
app.include_router(platform.router)

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
