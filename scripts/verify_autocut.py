"""Verify build_auto_cut + find demo reels that actually have dead air to cut.

    python -m scripts.verify_autocut
"""
from __future__ import annotations

from sqlalchemy import func, select

from api.routers.videos import _cutplan_benchmark, _video_context
from creative_director.advice.cutplan import build_auto_cut
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoTimeline


def _candidates(limit: int = 40) -> list[str]:
    with session_scope() as s:
        rows = s.execute(
            select(Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoTimeline, VideoTimeline.video_id == Video.id)
            .where(Channel.niche == "ig_fitness")
            .group_by(Video.id)
            .having(func.count(VideoTimeline.second) >= 10)
            .order_by(func.count(VideoTimeline.second).desc())
            .limit(limit)
        ).all()
        return [r[0] for r in rows]


def main() -> None:
    found = 0
    for vid in _candidates():
        niche, tier, archetype = _video_context(vid)
        if niche is None:
            continue
        with session_scope() as s:
            v = s.get(Video, vid)
            category = v.category if v else None
        bm = _cutplan_benchmark(niche, tier, archetype, category)
        cut = build_auto_cut(vid, bm)
        if cut is None:
            continue
        if cut["changed"]:
            found += 1
            print(
                f"{vid}  {archetype:<7} cat={category or '-':<12} "
                f"{cut['original_duration']}s -> {cut['new_duration']}s "
                f"(-{cut['removed_seconds']}s)  segs={len(cut['segments'])}"
            )
            for rm in cut["removed"]:
                print(f"     cut {rm['start']}-{rm['end']}s: {rm['reason']}")
            if found >= 8:
                break

    if found == 0:
        print("No reels with dead air found in the sample (all already tight).")


if __name__ == "__main__":
    main()
