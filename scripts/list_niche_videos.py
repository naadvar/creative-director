"""Emit the R2 video filenames for a niche, for `rclone --files-from`.

Lets the pod pull just one niche's videos at a time (so a small pod disk can
hold the corpus piecewise). Filenames are relative to the bucket's videos/
prefix, e.g. ``ig_DXxxxx.mp4``.

    python -m scripts.list_niche_videos --niche ig_food --out /tmp/ig_food.txt
"""
from __future__ import annotations

from pathlib import Path

import typer
from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video

app = typer.Typer(add_completion=False)


@app.command()
def main(
    niche: str = typer.Option(..., help="Niche tag, e.g. ig_food"),
    out: Path = typer.Option(..., help="File to write the rclone --files-from list to"),
):
    with session_scope() as s:
        ids = (
            s.execute(
                select(Video.id)
                .join(Channel, Channel.id == Video.channel_id)
                .where(Channel.niche == niche)
            )
            .scalars()
            .all()
        )
    out.write_text("\n".join(f"{vid}.mp4" for vid in ids) + "\n", encoding="utf-8")
    print(f"{niche}: wrote {len(ids)} filenames -> {out}")


if __name__ == "__main__":
    app()
