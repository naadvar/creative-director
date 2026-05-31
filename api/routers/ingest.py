"""Single-URL ingest — paste a Shorts URL, get it into the analyzable corpus.

The download + CLIP/Whisper feature extraction is the slow path (~45-90s on
CPU); this endpoint blocks until it finishes. A background job queue is the
eventual upgrade — out of scope for the scaffold.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from api import schemas
from api.config import api_settings

router = APIRouter(tags=["ingest"])

_YT_ID = re.compile(r"(?:shorts/|watch\?v=|youtu\.be/|/v/|embed/)([A-Za-z0-9_-]{11})")


def parse_video_id(text: str) -> str | None:
    """Pull an 11-char YouTube ID out of a URL, or accept a bare ID."""
    text = (text or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    m = _YT_ID.search(text)
    return m.group(1) if m else None


@router.post("/analyze-url", response_model=schemas.IngestResponse)
def analyze_url(req: schemas.IngestRequest) -> schemas.IngestResponse:
    """Ingest one video by URL/ID so the /videos/{id}/* endpoints can analyze it.

    Idempotent: an already-ingested video returns immediately with cached=True
    (unless force=True). After a 200 here, fetch the /videos/{id}/* endpoints.
    """
    video_id = parse_video_id(req.url)
    if not video_id:
        raise HTTPException(
            status_code=422,
            detail="Could not parse a YouTube video ID from that input.",
        )

    # Heavy import (pulls in torch / whisper / clip) — deferred to the first
    # ingest so server startup and the analysis endpoints stay light.
    from creative_director.ingestion.single import ingest_single_video

    messages: list[str] = []
    try:
        result = ingest_single_video(
            video_id,
            niche=api_settings.niche,
            force=req.force,
            progress=messages.append,
        )
    except ValueError as exc:
        # Not a Short, not found, deleted/private — a client-input problem.
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # surface download / YouTube-API failures cleanly
        raise HTTPException(status_code=502, detail=f"Ingest failed: {exc}")

    return schemas.IngestResponse(
        video_id=video_id,
        cached=bool(result.get("cached")),
        duration=result.get("duration"),
        messages=messages,
    )
