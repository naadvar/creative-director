"""POST /events — frontend tap telemetry (copy/share/etc).

Server-side events are logged where they happen (auth, upload job, read fetch);
this endpoint exists ONLY for interactions that never hit the API otherwise.
Anonymous-safe, name-whitelisted (this is a counter, not an ingestion surface),
and always returns ok — a telemetry problem must never surface to the client."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.auth import get_optional_user
from creative_director.storage.telemetry import log_event

router = APIRouter(tags=["events"])

_ALLOWED = {
    "copy_checklist",
    "share_tapped",
    "app_opened",
    "idea_planned",
    "copy_caption",
    # An anonymous visitor tapped "See an example read first" from the sign-in wall.
    "example_read_viewed",
}


class EventBody(BaseModel):
    name: str
    video_id: Optional[str] = None


@router.post("/events")
def track(body: EventBody, request: Request) -> dict:
    if body.name in _ALLOWED:
        user = get_optional_user(request)
        log_event(
            body.name,
            user_id=user["id"] if user else None,
            video_id=(body.video_id or None),
        )
    return {"ok": True}
