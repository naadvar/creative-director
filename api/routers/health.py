"""Health check and API root."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["meta"])


@router.get("/")
def root() -> dict:
    return {"name": "Creative Director API", "docs": "/docs"}


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
