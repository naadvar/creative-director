"""How many velocity snapshots do we have per video, and over what time spans?

If IG reels were ingested 2026-05-21 and the velocity cron has been running
daily, each IG reel should have ~1-2 snapshots so far -- not enough for a
growth-curve label. Check before promising the velocity move.
"""
from collections import Counter

from sqlalchemy import func, select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, VelocitySnapshot, Video


def main() -> None:
    with session_scope() as s:
        # Snapshots per video, scoped to ig_fitness and fitness.
        for niche in ("ig_fitness", "fitness"):
            rows = s.execute(
                select(
                    Video.id,
                    func.count(VelocitySnapshot.id).label("n_snaps"),
                    func.max(VelocitySnapshot.hours_since_publish).label("max_age_h"),
                )
                .join(Channel, Channel.id == Video.channel_id)
                .outerjoin(VelocitySnapshot, VelocitySnapshot.video_id == Video.id)
                .where(Channel.niche == niche)
                .group_by(Video.id)
            ).all()
            n_total = len(rows)
            counts = Counter()
            ages = []
            for _vid, n, max_age in rows:
                counts[n] += 1
                if max_age:
                    ages.append(float(max_age))

            print(f"\n=== {niche}: {n_total} videos ===")
            print("Snapshots-per-video histogram:")
            for k in sorted(counts):
                print(f"  {k:>3} snaps : {counts[k]:>5}  ({100*counts[k]/n_total:5.1f}%)")

            if ages:
                ages.sort()
                n = len(ages)
                print(f"\nMax age of latest snapshot (hours), among videos with any snapshot:")
                print(f"  n={n}  min={ages[0]:.1f}  p25={ages[n//4]:.1f}  med={ages[n//2]:.1f}  "
                      f"p75={ages[(3*n)//4]:.1f}  max={ages[-1]:.1f}")

            # Coverage for a "early growth curve" definition: videos with at
            # least 3 snapshots whose first snapshot is < 48h after publish
            # and the latest is > 48h after publish (so we see early growth).
            eligible = sum(
                1 for _vid, n, max_age in rows
                if n is not None and n >= 3 and (max_age or 0) > 48
            )
            print(
                f"\nVideos eligible for an early-growth-curve label "
                f"(n>=3 snaps, span>48h): {eligible} ({100*eligible/n_total:.1f}%)"
            )


if __name__ == "__main__":
    main()
