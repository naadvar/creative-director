"""Iterate a profile's reels (video posts), newest first."""
from __future__ import annotations

from typing import Iterator

import instaloader


def iter_reels(
    profile: instaloader.Profile, max_reels: int = 60
) -> Iterator[instaloader.Post]:
    """Yield up to ``max_reels`` video posts (reels) from a profile.

    Carousels (GraphSidecar) are skipped — only single-video posts, which is
    what a reel is. Posts come newest-first from instaloader.
    """
    yielded = 0
    for post in profile.get_posts():
        if not post.is_video or post.typename != "GraphVideo":
            continue
        yield post
        yielded += 1
        if yielded >= max_reels:
            break
