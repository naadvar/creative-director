"""Smoke-test: compute_benchmark with tier param and print n_high per (tier, archetype)."""
from creative_director.advice.benchmark import compute_benchmark
from creative_director.advice.tier import TIERS


def main() -> None:
    for niche in ("ig_fitness",):
        print(f"\n=== {niche} ===")
        pooled = compute_benchmark(niche=niche)
        print(f"  pooled        n_total={pooled['n_total']}")
        for arch, data in pooled["archetypes"].items():
            print(f"    {arch:8} high={data['n_high']:>4}  low={data['n_low']:>4}")

        for tier in TIERS:
            bm = compute_benchmark(niche=niche, tier=tier)
            print(f"  tier={tier:<6} n_total={bm['n_total']}")
            for arch, data in bm["archetypes"].items():
                print(f"    {arch:8} high={data['n_high']:>4}  low={data['n_low']:>4}")


if __name__ == "__main__":
    main()
