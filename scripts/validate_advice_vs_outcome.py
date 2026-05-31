"""Empirical sanity check: does the dashboard's off-benchmark count match
actual performance?

For every labeled ig_fitness reel we compute its breakdown vs the same-tier,
same-archetype winner benchmark and count how many features are
off-benchmark. Then we tabulate that count against the actual outcome
tercile (0 low / 1 mid / 2 high) on `views_per_sub_aged_v1`.

If the dashboard's advice were tightly coupled to outcome, low-tercile reels
would have many off-benchmark findings and high-tercile reels would have
few. The middle tercile blurs both ways. We also surface the worst
disagreements -- high-performing reels that LOOK like they should fail
(many off-benchmark) and low-performing reels that LOOK like they should
win (few off-benchmark). These are the cases the dashboard would steer
wrong.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from sqlalchemy import select

from creative_director.advice.benchmark import (
    REPORTABLE,
    classify_archetype,
    compute_benchmark,
)
from creative_director.advice.tier import TIERS, tier_for_count
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel


LABEL_SCHEME = "views_per_sub_aged_v1"
NICHE = "ig_fitness"
MIN_TIER_WINNERS = 5  # match the API's pooled-fallback threshold


def _video_feature_value(video: Video, feature: str) -> Optional[float]:
    meta = REPORTABLE[feature]
    src = meta["source"]
    if src == "video":
        v = getattr(video, feature, None)
    else:
        v = getattr(video.features, feature, None) if video.features else None
    return None if v is None else float(v)


def main() -> None:
    # 1. Build tier-stratified benchmarks (mirrors the API cache).
    print(f"Building benchmarks for {NICHE} ...")
    bms: dict[Optional[str], dict] = {}
    for t in TIERS:
        bms[t] = compute_benchmark(label_scheme=LABEL_SCHEME, niche=NICHE, tier=t)
    bms[None] = compute_benchmark(label_scheme=LABEL_SCHEME, niche=NICHE)

    # 2. Iterate every labeled reel.
    with session_scope() as s:
        rows = s.execute(
            select(Video, VideoFeatures, Channel, VideoLabel)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .join(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme == LABEL_SCHEME),
            )
            .where(Channel.niche == NICHE)
        ).all()
        print(f"Scanning {len(rows)} labeled {NICHE} reels ...")

        # Per row: tercile, off_count, total measured, sum_gap, max_gap
        records = []
        for video, feat, channel, label in rows:
            archetype = classify_archetype(feat.transcript_word_count)
            tier = tier_for_count(channel.subscriber_count)
            # Same pick-for-tier logic as the API: use tier-specific if it has
            # >= MIN_TIER_WINNERS for the archetype, else pool.
            chosen_bm = bms.get(tier) if tier else None
            if chosen_bm:
                arch_data = chosen_bm["archetypes"].get(archetype, {})
                if arch_data.get("n_high", 0) < MIN_TIER_WINNERS:
                    chosen_bm = bms[None]
            else:
                chosen_bm = bms[None]
            profile = chosen_bm["archetypes"].get(archetype, {}).get("profile", {})

            off_count = 0
            total_measured = 0
            sum_gap = 0.0
            max_gap = 0.0
            for f_name in REPORTABLE:
                if f_name not in profile:
                    continue
                bm = profile[f_name]["high_median"]
                val = _video_feature_value(video, f_name)
                if val is None:
                    continue
                total_measured += 1
                if bm > 0:
                    gap_ratio = val / bm
                else:
                    gap_ratio = 1.0 if val == bm else 2.0
                gap_mag = abs(gap_ratio - 1.0)
                if gap_mag > 0.25:
                    off_count += 1
                    sum_gap += gap_mag
                    max_gap = max(max_gap, gap_mag)

            records.append(
                {
                    "video_id": video.id,
                    "title": video.title.strip(),
                    "channel": channel.title,
                    "subs": channel.subscriber_count,
                    "tier": tier or "unknown",
                    "archetype": archetype,
                    "tercile": int(label.tercile),
                    "score": float(label.score),
                    "off_count": off_count,
                    "total_measured": total_measured,
                    "sum_gap": sum_gap,
                    "max_gap": max_gap,
                }
            )

    # 3. Cross-tab: off_count distribution by tercile.
    print()
    print("=" * 72)
    print("OFF-BENCHMARK COUNT DISTRIBUTION BY ACTUAL TERCILE")
    print("=" * 72)
    print("(if advice tracks outcome perfectly, high-tercile rows lean LOW;")
    print(" low-tercile rows lean HIGH. random noise = identical columns.)")
    print()
    by_tercile: dict[int, Counter] = {0: Counter(), 1: Counter(), 2: Counter()}
    for r in records:
        by_tercile[r["tercile"]][r["off_count"]] += 1
    header = f"  {'off_count':>10} " + "".join(f"{name:>10}" for name in ("low", "mid", "high"))
    print(header)
    max_off = max(max(by_tercile[t]) for t in (0, 1, 2))
    for off in range(max_off + 1):
        c = [by_tercile[t][off] for t in (0, 1, 2)]
        if sum(c) == 0:
            continue
        print(f"  {off:>10} " + "".join(f"{n:>10d}" for n in c))

    # 4. Means + percentiles for a numeric summary.
    def stats(values: list[float]) -> str:
        if not values:
            return "n=0"
        values = sorted(values)
        n = len(values)
        return (
            f"n={n} mean={sum(values)/n:5.2f} "
            f"p25={values[n//4]:.0f} med={values[n//2]:.0f} p75={values[(3*n)//4]:.0f}"
        )

    print()
    print("OFF-BENCHMARK COUNTS PER TERCILE:")
    for t, name in [(0, "low"), (1, "mid"), (2, "high")]:
        vals = [r["off_count"] for r in records if r["tercile"] == t]
        print(f"  {name:<5} : {stats(vals)}")

    print()
    print("SUM-OF-GAP-MAGNITUDES PER TERCILE:")
    for t, name in [(0, "low"), (1, "mid"), (2, "high")]:
        vals = [r["sum_gap"] for r in records if r["tercile"] == t]
        print(f"  {name:<5} : n={len(vals)} mean_sum_gap={sum(vals)/max(1, len(vals)):5.2f}")

    # 5. Outliers.
    print()
    print("=" * 72)
    print("OUTLIERS: HIGH-TERCILE REELS WITH THE MOST OFF-BENCHMARK FINDINGS")
    print("=" * 72)
    print("(if these exist, the dashboard would have warned a creator AWAY")
    print(" from a recipe that actually worked. that's a model error.)")
    print()
    high_disagree = sorted(
        [r for r in records if r["tercile"] == 2],
        key=lambda r: (-r["off_count"], -r["sum_gap"]),
    )[:10]
    print(f"  {'video_id':<24} {'tier':<6} {'arch':<8} {'score':>6} {'off':>4} {'sum_gap':>8}  channel  -- title")
    for r in high_disagree:
        print(
            f"  {r['video_id']:<24} {r['tier']:<6} {r['archetype']:<8} "
            f"{r['score']:>+6.2f} {r['off_count']:>4d} {r['sum_gap']:>8.2f}  "
            f"{r['channel'][:22]} -- {r['title'][:60]}"
        )

    print()
    print("=" * 72)
    print("OUTLIERS: LOW-TERCILE REELS WITH THE FEWEST OFF-BENCHMARK FINDINGS")
    print("=" * 72)
    print("(if these exist, the reel looked 'good' on every dimension we")
    print(" measure but still bombed -- the features don't capture what")
    print(" actually matters for it. dashboard advice would have over-praised.)")
    print()
    low_disagree = sorted(
        [r for r in records if r["tercile"] == 0],
        key=lambda r: (r["off_count"], r["sum_gap"]),
    )[:10]
    print(f"  {'video_id':<24} {'tier':<6} {'arch':<8} {'score':>6} {'off':>4} {'sum_gap':>8}  channel  -- title")
    for r in low_disagree:
        print(
            f"  {r['video_id']:<24} {r['tier']:<6} {r['archetype']:<8} "
            f"{r['score']:>+6.2f} {r['off_count']:>4d} {r['sum_gap']:>8.2f}  "
            f"{r['channel'][:22]} -- {r['title'][:60]}"
        )


if __name__ == "__main__":
    main()
