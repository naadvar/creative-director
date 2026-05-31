"""instaloader session setup for the Instagram ingestion path.

PERSONAL-V1 ONLY. Use a BURNER account, never your main one — scraping puts the
account at risk of limits/bans. The loader is configured conservatively
(built-in pacing, metadata only, no instaloader-side file downloads) because
Instagram blocks fast scrapers quickly.
"""
from __future__ import annotations

from typing import Optional

import instaloader
from loguru import logger

from creative_director.config import settings

_loader: Optional[instaloader.Instaloader] = None


def get_instaloader() -> instaloader.Instaloader:
    """Return a process-wide instaloader session (logs in if a burner is set)."""
    global _loader
    if _loader is not None:
        return _loader

    loader = instaloader.Instaloader(
        quiet=True,
        # We pull metadata + media URLs ourselves; disable instaloader's own
        # file-writing side effects.
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        sleep=True,  # built-in pacing between requests — keep it on
        max_connection_attempts=2,
        request_timeout=30.0,
    )

    user = settings.instagram_user
    password = settings.instagram_password
    if user and password:
        try:
            loader.login(user, password)
            logger.info(f"instaloader: logged in as burner '{user}'")
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"instaloader login failed ({e}) — continuing anonymously. "
                f"Anonymous access is heavily rate-limited by Instagram."
            )
    else:
        logger.info(
            "instaloader: anonymous mode. Set INSTAGRAM_USER / INSTAGRAM_PASSWORD "
            "in .env (a BURNER account) if Instagram blocks anonymous requests."
        )

    _loader = loader
    return loader
