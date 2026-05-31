"""Cached, tier-stratified, niche-aware benchmark provider.

The advice layer's three benchmarks each scan the whole winner corpus -- too
slow to recompute per request. We compute FOUR copies of each (small, mid,
large, pooled) per niche so a creator can be compared against winners in
their follower-count tier AND their content niche. ``pooled`` is the
fallback when a (tier, archetype) bucket is too thin to stand on its own.

Each method returns a {tier: benchmark, "pooled": benchmark} dict for the
caller's niche. The depended-on label+niche set rarely changes, so we cache
per (niche) lazily; ``refresh()`` drops everything after an offline label
recompute.
"""
from __future__ import annotations

import threading
from typing import Optional

from creative_director.advice.benchmark import compute_benchmark
from creative_director.advice.tier import TIERS
from creative_director.advice.timeline_benchmark import (
    compute_per_second_benchmark,
    compute_timeline_benchmark,
)

from api.config import api_settings


# Minimum (tier, archetype) winner count below which a route should pick the
# pooled benchmark for that creator. The per-tier benchmark is still computed
# so we always have something to fall back to.
_MIN_TIER_WINNERS = 5


def _build_tier_map(compute_fn, niche: str) -> dict[str, dict]:
    """Compute the same benchmark function four times: once per tier + pooled."""
    out: dict[str, dict] = {}
    for tier in TIERS:
        out[tier] = compute_fn(
            label_scheme=api_settings.label_scheme,
            niche=niche,
            tier=tier,
        )
    out["pooled"] = compute_fn(
        label_scheme=api_settings.label_scheme,
        niche=niche,
        tier=None,
    )
    return out


def pick_for_tier(
    by_tier: dict[str, dict],
    creator_tier: Optional[str],
    archetype: Optional[str] = None,
) -> tuple[dict, str]:
    """Pick a tier-specific benchmark if it has enough winners, else pooled.

    Returns ``(benchmark, scope)`` where scope is "tier" or "pooled" so the
    caller can surface which one was used.
    """
    if creator_tier and creator_tier in by_tier:
        candidate = by_tier[creator_tier]
        if archetype is None:
            return candidate, "tier"
        n_high = (
            candidate.get("archetypes", {}).get(archetype, {}).get("n_high")
            or candidate.get("archetypes", {}).get(archetype, {}).get("n_winners")
            or 0
        )
        if n_high >= _MIN_TIER_WINNERS:
            return candidate, "tier"
    return by_tier["pooled"], "pooled"


class BenchmarkCache:
    """Lazily computes and caches per-niche, per-tier benchmarks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._aggregate: dict[str, dict[str, dict]] = {}
        self._timeline: dict[str, dict[str, dict]] = {}
        self._per_second: dict[str, dict[str, dict]] = {}
        # (niche, tier, category) -> timeline benchmark, computed on demand for
        # the cut-plan (category winners where data allows).
        self._timeline_cat: dict[tuple, dict] = {}

    def timeline_category(
        self, niche: Optional[str], tier: Optional[str], category: Optional[str]
    ) -> dict:
        niche = self._resolve_niche(niche)
        key = (niche, tier, category)
        if key not in self._timeline_cat:
            with self._lock:
                if key not in self._timeline_cat:
                    self._timeline_cat[key] = compute_timeline_benchmark(
                        label_scheme=api_settings.label_scheme,
                        niche=niche,
                        tier=tier,
                        category=category,
                    )
        return self._timeline_cat[key]

    def _resolve_niche(self, niche: Optional[str]) -> str:
        return niche or api_settings.niche

    def aggregate(self, niche: Optional[str] = None) -> dict[str, dict]:
        """High-vs-low feature profiles per tier in the given niche."""
        niche = self._resolve_niche(niche)
        if niche not in self._aggregate:
            with self._lock:
                if niche not in self._aggregate:
                    self._aggregate[niche] = _build_tier_map(
                        compute_benchmark, niche
                    )
        return self._aggregate[niche]

    def timeline(self, niche: Optional[str] = None) -> dict[str, dict]:
        """Hook + pacing winner profile per tier in the given niche."""
        niche = self._resolve_niche(niche)
        if niche not in self._timeline:
            with self._lock:
                if niche not in self._timeline:
                    self._timeline[niche] = _build_tier_map(
                        compute_timeline_benchmark, niche
                    )
        return self._timeline[niche]

    def per_second(self, niche: Optional[str] = None) -> dict[str, dict]:
        """Per-second winner profile per tier in the given niche."""
        niche = self._resolve_niche(niche)
        if niche not in self._per_second:
            with self._lock:
                if niche not in self._per_second:
                    self._per_second[niche] = _build_tier_map(
                        compute_per_second_benchmark, niche
                    )
        return self._per_second[niche]

    def warm(self, niche: Optional[str] = None) -> None:
        """Compute all three for one niche up front."""
        self.aggregate(niche)
        self.timeline(niche)
        self.per_second(niche)

    def refresh(self) -> None:
        """Drop all cached benchmarks -- call after an offline label recompute."""
        with self._lock:
            self._aggregate.clear()
            self._timeline.clear()
            self._per_second.clear()
            self._timeline_cat.clear()


benchmarks = BenchmarkCache()
