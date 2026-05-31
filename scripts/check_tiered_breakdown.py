"""Smoke-test: run analyze_video with tier-stratified benchmarks on a real IG reel."""
from creative_director.advice.benchmark import compute_benchmark
from creative_director.advice.breakdown import analyze_video
from creative_director.advice.tier import TIERS, tier_for_video
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video


def _pick_video(niche: str = "ig_fitness") -> str:
    """First reel from a SMALL-tier creator with full features (deterministic-ish)."""
    from sqlalchemy import select

    with session_scope() as s:
        rows = s.execute(
            select(Video.id)
            .join(Channel, Video.channel_id == Channel.id)
            .where(
                (Channel.niche == niche)
                & (Channel.subscriber_count < 100_000)
            )
            .order_by(Video.id)
            .limit(50)
        ).scalars().all()
    return rows[3]  # pick a deterministic-but-arbitrary index


def main() -> None:
    niche = "ig_fitness"
    print(f"Building tier-stratified benchmarks for {niche} ...")
    benchmarks_by_tier: dict[str, dict] = {}
    for tier in TIERS:
        benchmarks_by_tier[tier] = compute_benchmark(niche=niche, tier=tier)
    benchmarks_by_tier["pooled"] = compute_benchmark(niche=niche)

    vid = _pick_video(niche)
    with session_scope() as s:
        tier = tier_for_video(s, vid)
    print(f"\nAnalyzing {vid}  (creator tier: {tier})")

    bd = analyze_video(vid, benchmarks_by_tier=benchmarks_by_tier)
    print(f"  archetype: {bd.archetype}  (n_high backing: {bd.archetype_n})")
    print(f"  benchmark_scope: {bd.benchmark_scope}   creator_tier: {bd.tier}")
    print(f"  tercile: {bd.tercile}  score: {bd.score}")
    print()
    print(f"  {'feature':<24} {'your':>10}  {'bench':>10}  {'gap_ratio':>10}  "
          f"{'fix':<7} {'rank':>6}  off  causal")
    for f in bd.findings:
        yv = f"{f.your_value:.1f}" if f.your_value is not None else "n/a"
        print(
            f"  {f.feature:<24} {yv:>10}  {f.benchmark_value:>10.1f}  "
            f"{f.gap_ratio:>10.3f}  {f.fixability:<7} {f.rank_score:>6.3f}  "
            f"{'YES' if f.off_benchmark else ' . '}  {f.causal}"
        )


if __name__ == "__main__":
    main()
