"""log_event — the one-line telemetry hook.

Best-effort by contract: a telemetry failure must NEVER break a product path, so
this swallows everything and logs at debug. Keep event names short, stable, and
snake_case; they become the KPI vocabulary (storage/kpis.py):

  login            (method, new_user)      auth
  upload_started   (niche, revision, idea) upload accepted
  read_completed   (grounded, suppressed, transcoded, revision_state) job finished
  read_failed      (error)                 job crashed
  read_viewed      (is_upload)             read page fetched
  upload_deleted                           creator removed a reel
  copy_checklist / share_tapped            frontend taps (POST /events)
"""
from __future__ import annotations

import json
from typing import Optional

from loguru import logger

from creative_director.storage.db import session_scope
from creative_director.storage.models import Event


def log_event(
    name: str,
    *,
    user_id: Optional[int] = None,
    video_id: Optional[str] = None,
    **props,
) -> None:
    try:
        clean = {k: v for k, v in props.items() if v is not None}
        # keep rows tiny — this is a counter, not a payload store
        if clean and len(json.dumps(clean)) > 1000:
            clean = {"_truncated": True}
        with session_scope() as s:
            s.add(
                Event(
                    name=str(name)[:48],
                    user_id=user_id,
                    video_id=(str(video_id)[:64] if video_id else None),
                    props=clean or None,
                )
            )
    except Exception as e:  # noqa: BLE001 — telemetry must never take down a request
        logger.debug(f"telemetry drop ({name}): {type(e).__name__}")
