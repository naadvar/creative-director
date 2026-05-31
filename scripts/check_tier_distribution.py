"""Quick sanity check: print per-niche tier distribution."""
from creative_director.advice.tier import tier_distribution
from creative_director.storage.db import session_scope


def main() -> None:
    with session_scope() as s:
        for niche in ("fitness", "ig_fitness"):
            d = tier_distribution(s, niche=niche)
            total = sum(d.values())
            print(f"\n{niche}: total={total}")
            for k, v in d.items():
                pct = 100.0 * v / total if total else 0.0
                print(f"  {k:<8} {v:>6}  ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
