"""
main.py — FastAPI application entry point.
Serves the API and static frontend from one process.

Run:
    uvicorn app.main:app --reload --port 8000
Then open:  http://localhost:8000/
Docs:       http://localhost:8000/docs
"""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes import alerts, audit, entities, graph, ingest, process, resolution, review

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Argus — SIH 2026 PS 26189",
    version="0.3.0",
    description=(
        "Cross-case entity resolution, link analysis and a multi-agency evidence chain "
        "for law enforcement. Zero external services — SQLite files, single terminal."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(ingest.router)
app.include_router(process.router)
app.include_router(entities.router)
app.include_router(graph.router)
app.include_router(review.router)
app.include_router(resolution.router)
app.include_router(alerts.router)
app.include_router(audit.router)

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health():
    """Liveness check."""
    return {"status": "ok", "service": "argus", "version": "0.3.0"}

# ── Static frontend ───────────────────────────────────────────────────────────

_FRONTEND = pathlib.Path(__file__).parent.parent.parent / "frontend"

if _FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(_FRONTEND / "index.html"))
