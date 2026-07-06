"""Session-based auth helpers.

Auth is via Instagram Login (no passwords). After the OAuth callback we store
``user_id`` in the signed-cookie session (Starlette SessionMiddleware, wired in
main.py). These helpers read it back and resolve the current ``User``.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jwt import PyJWKClient
from sqlalchemy import func, select

try:  # PyJWT >= 2.8 distinguishes JWKS transport errors; older versions don't.
    from jwt.exceptions import PyJWKClientConnectionError
except ImportError:  # pragma: no cover
    PyJWKClientConnectionError = None  # type: ignore[assignment, misc]

from api.config import api_settings
from creative_director.storage.db import session_scope
from creative_director.storage.models import ConnectedAccount, User

SESSION_USER_KEY = "user_id"

# Bearer token for native (Capacitor) clients: a WKWebView at capacitor://localhost
# can't send the signed-cookie session cross-origin to the API, so the app stores a
# token and sends it as `Authorization: Bearer`. Signed with the SAME secret as the
# session, so it's no weaker than the web cookie.
_TOKEN_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(api_settings.session_secret, salt="cd-bearer-auth")


def make_token(user_id: int) -> str:
    return _token_serializer().dumps(int(user_id))


def _user_id_from_token(token: str) -> Optional[int]:
    try:
        return int(_token_serializer().loads(token, max_age=_TOKEN_MAX_AGE))
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


# --- Sign in with Apple (native) -------------------------------------------------
# The iOS app gets an identity token (a JWT) from Apple and POSTs it to /auth/apple.
# We verify the RS256 signature against Apple's public keys plus the issuer, audience
# (our bundle id), and expiry. Native verification needs only the public JWKS — no
# Services ID or client secret (those are for web Apple login, which we don't do).
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_BUNDLE_ID = os.getenv("APPLE_BUNDLE_ID", "com.creativedirector.app")

_apple_jwk_client: Optional[PyJWKClient] = None


def _apple_jwks() -> PyJWKClient:
    """Lazily-built JWKS client. PyJWKClient caches fetched signing keys (1h here)
    so we don't hit Apple's key endpoint on every login."""
    global _apple_jwk_client
    if _apple_jwk_client is None:
        _apple_jwk_client = PyJWKClient(APPLE_JWKS_URL, cache_keys=True, lifespan=3600)
    return _apple_jwk_client


def verify_apple_identity_token(identity_token: str) -> dict:
    """Verify an Apple Sign-in identity token and return its claims.

    Raises HTTPException(401) for any invalid/expired/forged token, and 502 if
    Apple's key endpoint can't be reached (so the client can fall back to email).
    """
    try:
        signing_key = _apple_jwks().get_signing_key_from_jwt(identity_token)
        return jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=APPLE_BUNDLE_ID,
            issuer=APPLE_ISSUER,
            leeway=300,  # tolerate small clock skew on exp/iat
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True},
        )
    except jwt.PyJWKClientError as e:
        # A transient JWKS fetch failure -> 502 (retryable); anything else (no
        # matching key, malformed header) -> 401.
        if PyJWKClientConnectionError is not None and isinstance(
            e, PyJWKClientConnectionError
        ):
            raise HTTPException(
                status_code=502, detail="Could not reach Apple to verify sign-in"
            )
        raise HTTPException(status_code=401, detail="Invalid Apple sign-in")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid Apple sign-in")

# Pragmatic email shape check — not RFC-perfect, just enough to reject typos and
# junk at the passwordless gate (the email IS the lead-capture signal).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(raw: str) -> Optional[str]:
    e = (raw or "").strip().lower()
    return e if _EMAIL_RE.match(e) and len(e) <= 320 else None


def login_user(request: Request, user_id: int) -> None:
    """Mark the session as authenticated for this user."""
    request.session[SESSION_USER_KEY] = user_id


def logout_user(request: Request) -> None:
    request.session.pop(SESSION_USER_KEY, None)


def _current_user_id(request: Request) -> Optional[int]:
    # Native app: a Bearer token (cookies can't ride cross-origin from the webview).
    auth = request.headers.get("Authorization") or ""
    if auth[:7].lower() == "bearer ":
        uid = _user_id_from_token(auth[7:].strip())
        if uid is not None:
            return uid
    # Web: the signed-cookie session.
    uid = request.session.get(SESSION_USER_KEY)
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def get_optional_user(request: Request) -> Optional[dict]:
    """Return a lightweight dict for the logged-in user, or None.

    Returns a plain dict (not the ORM object) so it's safe to use after the
    session_scope closes and serializes cleanly into responses.
    """
    uid = _current_user_id(request)
    if uid is None:
        return None
    with session_scope() as s:
        user = s.get(User, uid)
        if user is None:
            return None
        conns = (
            s.execute(
                select(ConnectedAccount).where(ConnectedAccount.user_id == uid)
            )
            .scalars()
            .all()
        )
        return {
            "id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "connections": [
                {
                    "platform": c.platform,
                    "username": c.username,
                    "account_type": c.account_type,
                    "connected_at": c.connected_at.isoformat()
                    if c.connected_at
                    else None,
                }
                for c in conns
            ],
        }


def get_current_user(request: Request) -> dict:
    """Dependency that requires an authenticated user (401 otherwise)."""
    user = get_optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def email_login(request: Request, email: str) -> int:
    """Passwordless gate: find-or-create the User for this email, log them in,
    and return the user_id. The email is the lead-capture signal; there's no
    password, so this is a low-friction demo gate, not hardened account security."""
    now = datetime.utcnow()
    with session_scope() as s:
        user = (
            s.execute(select(User).where(func.lower(User.email) == email))
            .scalars()
            .first()
        )
        new_user = user is None
        if user is None:
            user = User(
                created_at=now, last_login_at=now, email=email,
                display_name=email.split("@", 1)[0],
            )
            s.add(user)
            s.flush()  # assign user.id
        else:
            user.last_login_at = now
        uid = user.id
    login_user(request, uid)
    from creative_director.storage.telemetry import log_event

    log_event("login", user_id=uid, method="email", new_user=new_user)
    return uid


def upsert_user_and_connection(
    *,
    platform: str,
    platform_user_id: str,
    username: Optional[str],
    account_type: Optional[str],
    access_token: Optional[str],
    token_expires_at: Optional[datetime],
    scopes: Optional[str],
) -> int:
    """Find-or-create the User for this platform identity and upsert the
    ConnectedAccount with fresh token data. Returns the user_id."""
    with session_scope() as s:
        conn = (
            s.execute(
                select(ConnectedAccount).where(
                    (ConnectedAccount.platform == platform)
                    & (ConnectedAccount.platform_user_id == platform_user_id)
                )
            )
            .scalars()
            .first()
        )
        now = datetime.utcnow()
        new_user = conn is None
        if conn is None:
            user = User(created_at=now, last_login_at=now, display_name=username)
            s.add(user)
            s.flush()  # assign user.id
            conn = ConnectedAccount(
                user_id=user.id,
                platform=platform,
                platform_user_id=platform_user_id,
            )
            s.add(conn)
        else:
            user = s.get(User, conn.user_id)
            if user is not None:
                user.last_login_at = now
                if username and not user.display_name:
                    user.display_name = username
        conn.username = username
        conn.account_type = account_type
        conn.access_token = access_token
        conn.token_expires_at = token_expires_at
        conn.scopes = scopes
        s.flush()
        uid = conn.user_id
    from creative_director.storage.telemetry import log_event

    log_event("login", user_id=uid, method=platform, new_user=new_user)
    return uid
