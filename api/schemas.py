"""Pydantic response models — the stable API contract.

These mirror the advice layer's dataclasses but are deliberately decoupled: the
React frontend is built against these schemas, so an internal dataclass change
doesn't silently break the API. ``from_attributes=True`` lets each model be
built straight from its dataclass with ``Model.model_validate(obj)``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _FromAttrs(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- analyze-video: VideoBreakdown ------------------------------------------


class Finding(_FromAttrs):
    feature: str
    label: str
    your_value: Optional[float]
    benchmark_value: float
    unit: str
    direction: str  # "above" | "below" | "aligned"
    gap_ratio: float
    confidence: str
    causal: str
    off_benchmark: bool
    fixability: str = "medium"  # "high" | "medium" | "low"
    rank_score: float = 0.0
    trajectory: Optional[str] = None  # "improving" | "stable" | "declining" | None


class VideoBreakdown(_FromAttrs):
    video_id: str
    title: str
    channel: str
    duration_seconds: Optional[int]
    archetype: str
    archetype_n: int
    label_scheme: Optional[str]
    tercile: Optional[int]
    score: Optional[float]
    tier: Optional[str] = None  # "small" | "mid" | "large" | None
    benchmark_scope: str = "pooled"  # "tier" | "pooled"
    findings: list[Finding]


# --- plain-English summary: PlainSummary ------------------------------------


class Suggestion(_FromAttrs):
    text: str
    clause: str
    gap: float
    is_proxy: bool


class PlainSummary(_FromAttrs):
    archetype: str
    read: str
    worth_trying: list[Suggestion]
    strengths: list[str]


# --- example library --------------------------------------------------------


class ExampleVideo(_FromAttrs):
    """A real winning reel that exemplifies the winner-typical value for a feature."""

    video_id: str
    title: str
    channel: str
    value: float
    benchmark_value: float
    duration_seconds: Optional[int]


class ExampleList(BaseModel):
    """Response for /videos/{id}/examples/{feature}."""

    feature: str
    benchmark_value: float
    examples: list[ExampleVideo]


# --- frame breakdown: FrameBreakdown ----------------------------------------


class FrameBreakdown(_FromAttrs):
    video_id: str
    title: str
    archetype: str
    duration: int
    findings: list[str]


# --- timeline / per-second deviation ----------------------------------------


class TimelineSecond(BaseModel):
    second: int
    deviation: Optional[float]
    reason: Optional[str]
    parts: dict[str, float] = Field(default_factory=dict)


class TimelineSummary(BaseModel):
    """Shape of the deviation curve, reduced to scalars (from summarize_deviation)."""

    dev_mean: float
    dev_max: float
    dev_worst_rel: float
    dev_hook_mean: float
    dev_body_mean: float
    dev_front_back: float
    dev_flagged_frac: float


class Timeline(BaseModel):
    video_id: str
    seconds: list[TimelineSecond]
    summary: Optional[TimelineSummary]


# --- corpus browse ----------------------------------------------------------


class CorpusVideo(BaseModel):
    video_id: str
    title: str
    channel: str
    thumbnail_url: Optional[str]
    duration_seconds: Optional[int]
    published_at: Optional[datetime]
    tercile: Optional[int]
    score: Optional[float]
    category: Optional[str] = None
    category_label: Optional[str] = None


class CorpusPage(BaseModel):
    label_scheme: str
    niche: str
    total: int
    count: int
    limit: int
    offset: int
    videos: list[CorpusVideo]


class CategoryCount(BaseModel):
    key: str
    label: str
    count: int


class CorpusFacets(BaseModel):
    """Category chips for the browse UI: each category present + its count."""

    total: int
    categories: list[CategoryCount]


class NicheInfo(BaseModel):
    niche: str          # raw key, e.g. "ig_food"
    label: str          # display label, e.g. "Food"
    platform: str       # "instagram" | "youtube"
    count: int          # analyzable videos in this niche


class NicheList(BaseModel):
    """Niches present in the corpus, for the Explore niche switcher."""

    niches: list[NicheInfo]


# --- single-URL ingest ------------------------------------------------------


class IngestRequest(BaseModel):
    url: str = Field(..., description="A YouTube Shorts URL or a bare 11-char video ID.")
    force: bool = Field(False, description="Re-ingest even if the video is already cached.")


class IngestResponse(BaseModel):
    video_id: str
    cached: bool
    duration: Optional[int] = None
    messages: list[str] = Field(default_factory=list)


# --- content category (classifier guess + creator override) -----------------


class CategoryOption(BaseModel):
    key: str
    label: str


class CategoryInfo(BaseModel):
    """Current category + override options for one video.

    ``current`` is what the analysis is benchmarked against (a creator-confirmed
    pick if one exists, else the keyword-classifier guess). ``confirmed`` is True
    once the creator has set it explicitly. ``options`` are pre-sorted by the
    classifier's likelihood so the dropdown surfaces the best guesses first.
    """

    video_id: str
    current: Optional[str]
    current_label: str
    confirmed: bool
    guess: Optional[str]
    options: list[CategoryOption]


class CategoryUpdate(BaseModel):
    category: Optional[str] = Field(
        None, description="Category key to set, or null to clear (uncategorized)."
    )
