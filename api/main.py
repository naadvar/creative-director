"""Creative Director API — FastAPI backend wrapping the creative_director pipeline.

Run from the project root (so the SQLite relative path resolves):

    .venv/Scripts/python.exe -m api
    # or, equivalently:
    .venv/Scripts/python.exe -m uvicorn api.main:app --reload

Endpoints:
  GET  /                       — API root
  GET  /health                 — health check
  GET  /corpus                 — browse the analyzable corpus
  GET  /videos/{id}/analyze     — aggregate breakdown (VideoBreakdown)
  GET  /videos/{id}/summary     — plain-English read (PlainSummary)
  GET  /videos/{id}/frame       — hook & pacing breakdown (FrameBreakdown)
  GET  /videos/{id}/timeline    — per-second deviation timeline
  POST /analyze-url             — ingest a single Shorts URL

Interactive docs at /docs.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.sessions import SessionMiddleware

from api.config import api_settings
from api.routers import (
    analyze_handle,
    auth,
    corpus,
    events,
    health,
    ingest,
    instagram,
    me,
    tools,
    upload,
    videos,
)
from creative_director.storage.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # idempotent — ensures the SQLite tables exist

    # Pre-warm benchmark caches in a daemon thread so the FIRST creator
    # analysis isn't a cold-cache 30-60s wait. The server accepts connections
    # immediately; the warm runs in the background (the per-benchmark locks
    # serialize any request that races it). Niche is the demo/active one.
    import threading

    def _warm() -> None:
        try:
            from api.benchmarks import benchmarks

            benchmarks.warm(api_settings.niche)
            benchmarks.warm("ig_fitness")
            logger.info("Benchmark caches warmed (fitness + ig_fitness)")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Benchmark warm failed (will warm lazily): {e}")

    threading.Thread(target=_warm, daemon=True).start()
    logger.info("Creative Director API ready (warming benchmarks in background)")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Creative Director API",
        version="0.1.0",
        description=(
            "Analyzes fitness YouTube Shorts against winning videos of the same "
            "content archetype. Findings are correlational, not proven causes."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Signed-cookie sessions for auth. same_site="lax" + https_only=False works
    # for local dev through the Vite /api proxy (same-origin). Tighten to
    # same_site="none" + https_only=True behind real HTTPS in production.
    app.add_middleware(
        SessionMiddleware,
        secret_key=api_settings.session_secret,
        same_site="lax",
        https_only=False,
        max_age=14 * 24 * 3600,
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(instagram.router)
    app.include_router(me.router)
    app.include_router(corpus.router)
    app.include_router(videos.router)
    # Private tester utilities (reel grabber). Self-gating: 404 unless API_TOOLS_KEY
    # is set, so including it unconditionally is inert in normal deploys.
    app.include_router(tools.router)
    # Frontend tap telemetry (whitelisted, anonymous-safe).
    app.include_router(events.router)
    # Heavy on-demand ingest (/analyze-url) pulls in torch/CLIP/Whisper on first
    # call. Gate it so the light serve-only deploy (corpus + advice from the
    # precomputed DB) can omit it entirely: set ENABLE_INGEST=false on that host.
    import os

    if os.getenv("ENABLE_INGEST", "true").lower() != "false":
        app.include_router(ingest.router)
        app.include_router(analyze_handle.router)
    # Upload-your-own-reel analysis (the compliant product path). Needs the full
    # extraction stack (torch/Whisper/CLIP) — disable on serve-only deploys.
    if os.getenv("ENABLE_UPLOAD", "true").lower() != "false":
        app.include_router(upload.router)
    return app


app = create_app()
