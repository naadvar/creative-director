"""Smoke-test the cut-plan layer end-to-end against the local DB.

    python -m scripts.verify_cutplan

Finds an ig_fitness video that actually has timeline rows, builds the pacing
benchmark the way the /cutplan route would, and prints both the full plan and a
trim recompute so we can eyeball that the numbers are sane before wiring the UI.
"""
from __future__ import annotations

from sqlalchemy import func, select

from api.benchmarks import benchmarks
from api.routers.videos import _cutplan_benchmark, _video_context
from creative_director.advice.cutplan import build_cut_plan, recompute_for_trim
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoTimeline


def _pick_video() -> str | None:
    """A real ig_fitness reel that has timeline rows AND a category set, so we
    exercise the category-aware benchmark path (the headline feature)."""
    with session_scope() as s:
        # categorized videos with the most timeline rows first
        row = s.execute(
            select(Video.id, Video.category, func.count(VideoTimeline.second))
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoTimeline, VideoTimeline.video_id == Video.id)
            .where(Channel.niche == "ig_fitness", Video.category.is_not(None))
            .group_by(Video.id)
            .order_by(func.count(VideoTimeline.second).desc())
            .limit(1)
        ).first()
        if row:
            return row[0]
        # fall back to any video with timeline rows
        row = s.execute(
            select(Video.id, func.count(VideoTimeline.second))
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoTimeline, VideoTimeline.video_id == Video.id)
            .where(Channel.niche == "ig_fitness")
            .group_by(Video.id)
            .order_by(func.count(VideoTimeline.second).desc())
            .limit(1)
        ).first()
        return row[0] if row else None


def main() -> None:
    vid = _pick_video()
    if vid is None:
        print("No ig_fitness video with timeline rows found locally.")
        return

    niche, tier, archetype = _video_context(vid)
    with session_scope() as s:
        v = s.get(Video, vid)
        category = v.category if v else None
    print(f"video={vid}  niche={niche}  tier={tier}  archetype={archetype}  category={category}")

    bm = _cutplan_benchmark(niche, tier, archetype, category)
    arch_bm = (bm.get("archetypes") or {}).get(archetype, {})
    print(f"benchmark category={bm.get('category')}  n_winners[{archetype}]={arch_bm.get('n_winners')}")
    print(f"  winner first_cut_median={arch_bm.get('first_cut_second_median')}  "
          f"cuts_per_10s_median={arch_bm.get('cuts_per_10s_median')}  "
          f"hook_face_pct={arch_bm.get('hook_face_pct')}")

    plan = build_cut_plan(vid, bm)
    print("\n=== CUT PLAN ===")
    if plan is None:
        print("  (none — no timeline)")
        return
    for k in (
        "archetype", "duration", "category", "benchmark_scope",
        "your_first_cut", "winner_first_cut", "winner_avg_shot",
        "your_hook_face_pct", "winner_hook_face_pct", "suggested_trim_start",
    ):
        print(f"  {k}: {plan[k]}")
    print(f"  your_cuts: {plan['your_cuts']}")
    print(f"  over_long_holds: {plan['over_long_holds']}")
    print("  suggestions:")
    for s_ in plan["suggestions"]:
        print(f"    - [{s_['type']} @{s_['second']}s] {s_['message']}")

    # Interactive recompute: try trimming to the suggested start (or 2s).
    trim = plan["suggested_trim_start"] or 2
    rc = recompute_for_trim(vid, bm, trim)
    print(f"\n=== RECOMPUTE @ trim_start={trim} ===")
    print(f"  aligned {rc['aligned']}/{rc['total']}")
    for c in rc["checks"]:
        print(f"    [{'PASS' if c['pass'] else 'FAIL'}] {c['label']}")


if __name__ == "__main__":
    main()
