"""Auth status + logout. Login happens via the Instagram OAuth router.

Also exposes a DEV-ONLY /auth/dev-login that signs in a demo creator without
OAuth (gated by api_settings.allow_dev_login) so the authed app can be
previewed against the existing corpus.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api.auth import (
    email_login,
    get_optional_user,
    login_user,
    logout_user,
    make_token,
    normalize_email,
    upsert_user_and_connection,
    verify_apple_identity_token,
)
from api.config import api_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class EmailLoginBody(BaseModel):
    email: str


class AppleLoginBody(BaseModel):
    identityToken: str
    # Apple returns the name only on the FIRST authorization, client-side (it is
    # NOT in the token), so the app forwards it for us to store as the display name.
    givenName: Optional[str] = None
    familyName: Optional[str] = None

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
    uid, new_user = email_login(request, email)
    # token: for native (Capacitor) clients that can't carry the session cookie.
    # The web app ignores it and keeps using the cookie.
    # new_user: lets the client catch a typo'd address (orphan account) before it
    # confirms — there's no email verification, so this is the only safety net.
    return {
        "user": get_optional_user(request),
        "token": make_token(uid),
        "new_user": new_user,
    }


@router.post("/apple")
def apple_gate(body: AppleLoginBody, request: Request) -> dict:
    """Native Sign in with Apple. Verify the identity token against Apple's public
    keys, then find-or-create the user by their stable Apple `sub`. Returns the
    same shape as /auth/email (so the frontend treats both logins identically)."""
    claims = verify_apple_identity_token(body.identityToken)
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=422, detail="Apple token missing subject")
    email = claims.get("email")
    is_private = str(claims.get("is_private_email", "")).lower() == "true"
    # Prefer the (first-login-only) name; else a non-relay email; else nothing.
    name = " ".join(p for p in (body.givenName, body.familyName) if p).strip()
    username = name or (email if email and not is_private else None)
    uid = upsert_user_and_connection(
        platform="apple",
        platform_user_id=str(sub),
        username=username,
        account_type=None,
        access_token=None,
        token_expires_at=None,
        scopes=None,
    )
    login_user(request, uid)
    return {"user": get_optional_user(request), "token": make_token(uid)}


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
