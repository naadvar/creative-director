"""Fetch Instagram creator profiles via instaloader."""
from __future__ import annotations

import instaloader


def fetch_profile(loader: instaloader.Instaloader, username: str) -> instaloader.Profile:
    """Resolve an Instagram @handle / username to a Profile object."""
    username = username.lstrip("@").strip().lower()
    return instaloader.Profile.from_username(loader.context, username)
