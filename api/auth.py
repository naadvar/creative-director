"""Session-based auth helpers.

Auth is via Instagram Login (no passwords). After the OAuth callback we store
``user_id`` in the signed-cookie session (Starlette SessionMiddleware, wired in
main.py). These helpers read it back and resolve the current ``User``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import ConnectedAccount, User

SESSION_USER_KEY = "user_id"


def login_user(request: Request, user_id: int) -> None:
    """Mark the session as authenticated for this user."""
    request.session[SESSION_USER_KEY] = user_id


def logout_user(request: Request) -> None:
    request.session.pop(SESSION_USER_KEY, None)


def _current_user_id(request: Request) -> Optional[int]:
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
        return conn.user_id
