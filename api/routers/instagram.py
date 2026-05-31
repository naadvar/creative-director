"""Instagram Login OAuth — "Instagram API with Instagram Login" (the current
post-Basic-Display path, for Professional/Creator accounts).

Flow:
  /auth/instagram/start     -> redirect to Instagram's authorize page (+CSRF state)
  /auth/instagram/callback  -> code -> short-lived token -> long-lived token
                               -> fetch profile -> upsert user + connection
                               -> set session -> redirect back to the SPA

Requires a Meta app (type Business) with the Instagram product, and the App
ID/secret in config (API_META_APP_ID / API_META_APP_SECRET). Meta requires an
HTTPS redirect URI, so for local dev point ``instagram_redirect_uri`` at a
cloudflared/ngrok HTTPS tunnel to this backend.

Endpoints can shift across Graph API versions; they're kept as constants here
so they're easy to adjust when first tested against a live app.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from loguru import logger

from api.auth import login_user, upsert_user_and_connection
from api.config import api_settings

router = APIRouter(prefix="/auth/instagram", tags=["auth"])

# Instagram Login (business) OAuth endpoints.
_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
_GRAPH = "https://graph.instagram.com"

_STATE_KEY = "ig_oauth_state"


def _require_config() -> None:
    if not api_settings.meta_app_id or not api_settings.meta_app_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Instagram OAuth is not configured. Set API_META_APP_ID and "
                "API_META_APP_SECRET (create a Meta app with the Instagram product)."
            ),
        )


@router.get("/start")
def start(request: Request) -> RedirectResponse:
    """Kick off the OAuth dance: store a CSRF state in the session and redirect
    the browser to Instagram's consent screen."""
    _require_config()
    state = secrets.token_urlsafe(24)
    request.session[_STATE_KEY] = state
    params = {
        "client_id": api_settings.meta_app_id,
        "redirect_uri": api_settings.instagram_redirect_uri,
        "response_type": "code",
        # New IG-business scopes are comma-separated.
        "scope": api_settings.instagram_scopes,
        "state": state,
    }
    return RedirectResponse(f"{_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """Handle Instagram's redirect: validate state, exchange the code for a
    long-lived token, fetch the profile, persist, and log the creator in."""
    _require_config()

    if error:
        logger.warning(f"IG OAuth error: {error}: {error_description}")
        return RedirectResponse(
            f"{api_settings.frontend_base_url}/?ig_error={error}"
        )

    expected = request.session.pop(_STATE_KEY, None)
    if not state or not expected or state != expected:
        raise HTTPException(status_code=400, detail="OAuth state mismatch (CSRF check failed).")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")

    with httpx.Client(timeout=30) as client:
        # 1. code -> short-lived token (+ the IG user id)
        tok = client.post(
            _TOKEN_URL,
            data={
                "client_id": api_settings.meta_app_id,
                "client_secret": api_settings.meta_app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": api_settings.instagram_redirect_uri,
                "code": code,
            },
        )
        if tok.status_code != 200:
            logger.error(f"IG token exchange failed: {tok.status_code} {tok.text}")
            raise HTTPException(status_code=400, detail="Token exchange failed.")
        tok_data = tok.json()
        short_token = tok_data.get("access_token")
        permissions = tok_data.get("permissions")

        # 2. short-lived -> long-lived token (~60 days)
        long_resp = client.get(
            f"{_GRAPH}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": api_settings.meta_app_secret,
                "access_token": short_token,
            },
        )
        if long_resp.status_code == 200:
            long_data = long_resp.json()
            access_token = long_data.get("access_token", short_token)
            expires_in = int(long_data.get("expires_in", 0)) or None
        else:
            logger.warning(
                f"Long-lived exchange failed ({long_resp.status_code}); using short token"
            )
            access_token = short_token
            expires_in = None

        # 3. fetch profile
        me = client.get(
            f"{_GRAPH}/{api_settings.instagram_graph_version}/me",
            params={
                "fields": "user_id,username,account_type",
                "access_token": access_token,
            },
        )
        if me.status_code != 200:
            logger.error(f"IG /me failed: {me.status_code} {me.text}")
            raise HTTPException(status_code=400, detail="Failed to fetch IG profile.")
        profile = me.json()

    platform_user_id = str(profile.get("user_id") or tok_data.get("user_id"))
    username = profile.get("username")
    account_type = profile.get("account_type")
    expires_at = (
        datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None
    )

    user_id = upsert_user_and_connection(
        platform="instagram",
        platform_user_id=platform_user_id,
        username=username,
        account_type=account_type,
        access_token=access_token,
        token_expires_at=expires_at,
        scopes=str(permissions) if permissions else api_settings.instagram_scopes,
    )
    login_user(request, user_id)
    logger.info(f"IG connected: @{username} ({account_type}) -> user {user_id}")
    return RedirectResponse(f"{api_settings.frontend_base_url}/?connected=instagram")
