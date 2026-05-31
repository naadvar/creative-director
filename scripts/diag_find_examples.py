"""Replicate the /examples endpoint EXACTLY in-process to find why the HTTP
route ignores category while a direct find_examples call respects it.

    python -m scripts.diag_find_examples
"""
from __future__ import annotations

from api.benchmarks import benchmarks, pick_for_tier
from api.config import api_settings
from api.routers.videos import _video_context
from creative_director.advice.examples import find_examples
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video

VID = "ig_DWPHyPBDvBM"
FEATURE = "duration_seconds"


def main() -> None:
    niche, tier, archetype = _video_context(VID)
    print(f"_video_context -> niche={niche!r} tier={tier!r} archetype={archetype!r}")

    bm_map = benchmarks.aggregate(niche)
    bm, scope = pick_for_tier(bm_map, tier, archetype)
    arch_data = bm.get("archetypes", {}).get(archetype, {}) if archetype else {}
    feat_profile = arch_data.get("profile", {}).get(FEATURE)
    if not feat_profile:
        pooled_arch = bm_map["pooled"].get("archetypes", {}).get(archetype, {})
        feat_profile = pooled_arch.get("profile", {}).get(FEATURE)
    benchmark_value = float(feat_profile["high_median"])
    print(f"benchmark_scope={scope!r}  benchmark_value={benchmark_value}")

    with session_scope() as s:
        video = s.get(Video, VID)
        category = video.category if video else None
        print(f"video.category={category!r}")
        results = find_examples(
            s,
            label_scheme=api_settings.label_scheme,
            niche=niche,
            feature=FEATURE,
            benchmark_value=benchmark_value,
            tier=tier,
            archetype=archetype,
            category=category,
            n=3,
            exclude_video_id=VID,
        )
        print("\nresults ->")
        for e in results:
            cat = s.get(Video, e.video_id).category
            print(f"  {e.video_id}  value={e.value}  category={cat!r}")


if __name__ == "__main__":
    main()
