"""FastAPI entry point.

Run locally:
    uvicorn trader_edge.server.main:app --reload --port 8000

Then open http://localhost:8000/ for the web UI or http://localhost:8000/docs
for the auto-generated API reference.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from .routes import analyze, chain, health, journal

app = FastAPI(
    title="trader-edge",
    description=(
        "Deterministic pre-trade risk engine for Indian equities and F&O. "
        "Uses the option chain as a free oracle for cash-segment trades. "
        "No LLMs in the reasoning loop."
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(analyze.router, prefix=API_PREFIX)
app.include_router(chain.router, prefix=API_PREFIX)
app.include_router(journal.router, prefix=API_PREFIX)

# Serve the static frontend if present
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"),
              name="assets") if (_STATIC_DIR / "assets").exists() else None
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")
