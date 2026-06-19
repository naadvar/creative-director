"""Corpus browse — the list of analyzable videos behind the React browse UI."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from api import schemas
from api.config import api_settings
from creative_director.advice.categories import label_for
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel

router = APIRouter(tags=["corpus"])


def _niche_label(niche: str) -> tuple[str, str]:
    """(display label, platform) derived from a niche key.

    IG niches are tagged ``ig_*``; everything else is treated as YouTube. Keeps
    the two platforms visibly separate in the switcher.
    """
    if niche.startswith("ig_"):
        return niche[3:].replace("_", " ").title(), "instagram"
    return niche.replace("_", " ").title(), "youtube"


@router.get("/corpus", response_model=schemas.CorpusPage)
def browse_corpus(
    tercile: Optional[int] = Query(
        None, ge=0, le=2, description="Filter to a performance tercile (0 low, 1 mid, 2 high)."
    ),
    niche: Optional[str] = Query(
        None, description="Filter to a niche (e.g. 'ig_fitness', 'ig_food')."
    ),
    category: Optional[str] = Query(
        None, description="Filter to a content category key (e.g. 'weights')."
    ),
    q: Optional[str] = Query(
        None, description="Free-text search over title + caption."
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> schemas.CorpusPage:
    """List analyzable videos, newest first.

    A video is analyzable iff it has extracted features — the metadata-only
    niches collected for velocity tracking are excluded by the inner join.
    Supports niche, category, and free-text filters so the browse grid can be
    sliced instead of being one flat list.
    """
    scheme = api_settings.label_scheme
    q_clean = (q or "").strip()

    with session_scope() as s:
        # Private uploads (synthetic upch_* channels) never appear in the browse.
        not_upload = Channel.id.notlike("upch_%")
        # Demo curation: only reels that went through Qwen (have a craft read).
        has_read = VideoFeatures.craft_read.isnot(None)
        require_read = api_settings.corpus_require_craft_read
        count_q = (
            select(func.count())
            .select_from(Video)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(not_upload)
        )
        rows_q = (
            select(Video, Channel.title, VideoLabel.tercile, VideoLabel.score)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .outerjoin(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme == scheme),
            )
            .where(not_upload)
        )
        if require_read:
            count_q = count_q.where(has_read)
            rows_q = rows_q.where(has_read)
        if niche:
            count_q = count_q.where(Channel.niche == niche)
            rows_q = rows_q.where(Channel.niche == niche)
        if tercile is not None:
            label_join = (
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme == scheme)
            )
            count_q = count_q.join(VideoLabel, label_join).where(
                VideoLabel.tercile == tercile
            )
            rows_q = rows_q.where(VideoLabel.tercile == tercile)
        if category:
            count_q = count_q.where(Video.category == category)
            rows_q = rows_q.where(Video.category == category)
        if q_clean:
            like = f"%{q_clean}%"
            text_match = or_(Video.title.ilike(like), Video.description.ilike(like))
            count_q = count_q.where(text_match)
            rows_q = rows_q.where(text_match)

        total = s.scalar(count_q) or 0
        rows = s.execute(
            rows_q.order_by(Video.published_at.desc()).limit(limit).offset(offset)
        ).all()

        videos = [
            schemas.CorpusVideo(
                video_id=v.id,
                title=v.title,
                channel=channel_title,
                thumbnail_url=v.thumbnail_url,
                duration_seconds=v.duration_seconds,
                published_at=v.published_at,
                tercile=terc,
                score=score,
                category=v.category,
                category_label=label_for(v.category) if v.category else None,
            )
            for v, channel_title, terc, score in rows
        ]

    return schemas.CorpusPage(
        label_scheme=scheme,
        niche=niche or api_settings.niche,
        total=total,
        count=len(videos),
        limit=limit,
        offset=offset,
        videos=videos,
    )


@router.get("/corpus/categories", response_model=schemas.CorpusFacets)
def corpus_categories(
    niche: Optional[str] = Query(None, description="Restrict counts to a niche."),
) -> schemas.CorpusFacets:
    """Category chips for the browse UI: every category present among analyzable
    videos (in the given niche), with its count, most-common first."""
    with session_scope() as s:
        not_upload = Channel.id.notlike("upch_%")
        total_q = (
            select(func.count())
            .select_from(Video)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(not_upload)
        )
        rows_q = (
            select(Video.category, func.count())
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(Video.category.is_not(None), not_upload)
            .group_by(Video.category)
            .order_by(func.count().desc())
        )
        if api_settings.corpus_require_craft_read:
            total_q = total_q.where(VideoFeatures.craft_read.isnot(None))
            rows_q = rows_q.where(VideoFeatures.craft_read.isnot(None))
        if niche:
            total_q = total_q.where(Channel.niche == niche)
            rows_q = rows_q.where(Channel.niche == niche)
        total = s.scalar(total_q) or 0
        rows = s.execute(rows_q).all()

    categories = [
        schemas.CategoryCount(key=cat, label=label_for(cat), count=n)
        for cat, n in rows
        if cat
    ]
    return schemas.CorpusFacets(total=total, categories=categories)


@router.get("/niches", response_model=schemas.NicheList)
def list_niches() -> schemas.NicheList:
    """Niches that have analyzable videos, with counts — drives the Explore
    niche switcher. A niche only appears once its videos have features (so a
    freshly-ingested, not-yet-extracted niche won't show a broken empty tab)."""
    with session_scope() as s:
        niche_q = (
            select(Channel.niche, func.count())
            .select_from(Video)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(Channel.niche.is_not(None), Channel.id.notlike("upch_%"))
            .group_by(Channel.niche)
            .order_by(func.count().desc())
        )
        if api_settings.corpus_require_craft_read:
            niche_q = niche_q.where(VideoFeatures.craft_read.isnot(None))
        rows = s.execute(niche_q).all()

    niches = []
    for niche, count in rows:
        if not niche:
            continue
        label, platform = _niche_label(niche)
        niches.append(
            schemas.NicheInfo(niche=niche, label=label, platform=platform, count=count)
        )
    return schemas.NicheList(niches=niches)
