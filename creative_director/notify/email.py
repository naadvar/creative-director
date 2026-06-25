"""Transactional email — the 'your read is ready' re-engagement nudge.

Inert by default: with no `resend_api_key` configured it logs and no-ops, so the
upload path is never blocked or broken by email. Set the key (and verify a sending
domain in Resend, or use the onboarding@resend.dev sandbox) to turn it on.
"""
from __future__ import annotations

from loguru import logger

from creative_director.config import settings


def send_read_ready(to_email: str, title: str, video_id: str) -> bool:
    """Send the one-line 'your craft read is ready' email with a deep link.
    Returns True if dispatched, False if skipped (no key) or failed — never raises,
    so a notification problem can't fail an otherwise-successful upload."""
    if not to_email or not settings.resend_api_key:
        logger.info("email nudge skipped (no resend_api_key or recipient)")
        return False
    url = f"{settings.app_base_url.rstrip('/')}/video/{video_id}"
    short = (title or "your reel").strip()[:80]
    html = (
        f'<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.6">'
        f'<p>Your craft read of <strong>{short}</strong> is ready.</p>'
        f'<p><a href="{url}" style="display:inline-block;background:#6d5efc;color:#fff;'
        f'padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:600">'
        f'See your read →</a></p>'
        f'<p style="color:#888;font-size:12px">A craft read of your footage — '
        f'no virality claims. Reply STOP to opt out.</p></div>'
    )
    try:
        import httpx

        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to_email],
                "subject": f"Your craft read is ready — {short}",
                "html": html,
            },
            timeout=20,
        )
        if r.status_code >= 300:
            logger.warning(f"email nudge failed ({r.status_code}): {r.text[:160]}")
            return False
        logger.info(f"email nudge sent to {to_email} for {video_id}")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"email nudge error: {type(e).__name__}: {e}")
        return False
