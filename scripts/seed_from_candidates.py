"""Append discovered creators to a niche seed YAML.

discover_ig_creators upserts every verified candidate as a Channel tagged
``{niche}_candidates``. This pulls the in-band ones (follower window), drops
obvious commerce/brand handles, dedupes against the existing seed, and appends
the survivors to the seed file's accounts list.

    python -m scripts.seed_from_candidates --niche ig_fashion \
        --seed-file seed_channels/instagram_fashion.yaml --limit 45
"""
from __future__ import annotations

import re
from pathlib import Path

import typer
import yaml
from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel

app = typer.Typer(add_completion=False)

# Handle substrings that signal a shop/brand/agency rather than a creator.
_BRAND = re.compile(
    r"(store|outlet|boutique|\bshop\b|official|oficial|brands|\.store|\.shop"
    r"|agency|tours|booking|\.de\b|\.my\b|\.ph\b)",
    re.IGNORECASE,
)


@app.command()
def main(
    niche: str = typer.Option(..., help="Target niche, e.g. ig_fashion"),
    seed_file: Path = typer.Option(..., help="Seed YAML to append to"),
    min_followers: int = typer.Option(5_000),
    max_followers: int = typer.Option(100_000),
    limit: int = typer.Option(45, help="Max creators to append (top by followers)"),
):
    cand_niche = f"{niche}_candidates"
    with session_scope() as s:
        rows = s.execute(
            select(Channel.handle, Channel.subscriber_count)
            .where(
                Channel.niche == cand_niche,
                Channel.subscriber_count >= min_followers,
                Channel.subscriber_count <= max_followers,
            )
            .order_by(Channel.subscriber_count.desc())
        ).all()

    data = yaml.safe_load(seed_file.read_text(encoding="utf-8")) or {}
    existing = {str(a).lstrip("@").lower() for a in (data.get("accounts") or [])}

    picks: list[tuple[str, int]] = []
    dropped_brand = 0
    for handle, subs in rows:
        h = (handle or "").lower()
        if not h or h in existing:
            continue
        if _BRAND.search(h):
            dropped_brand += 1
            continue
        picks.append((h, int(subs or 0)))
        if len(picks) >= limit:
            break

    if not picks:
        print(f"No new in-band candidates for {cand_niche}.")
        return

    block = "\n".join(f'  - "@{h}"  # {subs:,}' for h, subs in picks)
    text = seed_file.read_text(encoding="utf-8").rstrip() + "\n" + block + "\n"
    seed_file.write_text(text, encoding="utf-8")

    print(f"Appended {len(picks)} creators to {seed_file} "
          f"(in-band candidates: {len(rows)}, brand-dropped: {dropped_brand})")
    for h, subs in picks:
        print(f"  @{h:<28} {subs:>8,}")


if __name__ == "__main__":
    app()
