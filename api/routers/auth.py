"""Auth status + logout. Login happens via the Instagram OAuth router.

Also exposes a DEV-ONLY /auth/dev-login that signs in a demo creator without
OAuth (gated by api_settings.allow_dev_login) so the authed app can be
previewed against the existing corpus.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api.auth import (
    email_login,
    get_optional_user,
    login_user,
    logout_user,
    normalize_email,
    upsert_user_and_connection,
)
from api.config import api_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class EmailLoginBody(BaseModel):
    email: str

# Sentinel token marking the demo account; /me/reels serves corpus reels for it.
DEMO_TOKEN = "DEMO"


@router.get("/me")
def me(request: Request) -> dict:
    """Current auth state. Returns {"user": null} when not logged in (200, not
    401) so the SPA can check on load without treating it as an error."""
    return {"user": get_optional_user(request)}


@router.post("/email")
def email_gate(body: EmailLoginBody, request: Request) -> dict:
    """Passwordless email gate — the public demo's low-friction login + lead
    capture. Find-or-create the user by email, start a session, return them."""
    email = normalize_email(body.email)
    if email is None:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    email_login(request, email)
    return {"user": get_optional_user(request)}


@router.post("/logout")
def logout(request: Request) -> dict:
    logout_user(request)
    return {"ok": True}


@router.get("/dev-login")
def dev_login(request: Request) -> RedirectResponse:
    """DEV ONLY: sign in a demo creator (no OAuth) and redirect into the app.
    Their "Your Reels" is served from the existing corpus. Disabled in prod
    via API_ALLOW_DEV_LOGIN=false."""
    if not api_settings.allow_dev_login:
        raise HTTPException(status_code=404, detail="Not found")
    user_id = upsert_user_and_connection(
        platform="instagram",
        platform_user_id="demo",
        username="demo_creator",
        account_type="DEMO",
        access_token=DEMO_TOKEN,
        token_expires_at=None,
        scopes="demo",
    )
    login_user(request, user_id)
    # Relative redirect resolves to the visitor's OWN origin (the Vercel URL for a
    # remote visitor, localhost:5173 for local dev) — no config dependency, and it
    # never bounces a public visitor to the dev server.
    return RedirectResponse("/?demo=1")
