"""CLI: print the v0 creative-director breakdown for one or more videos.

    python -m scripts.analyze_video --video-id LmEWj_PPRsk
    python -m scripts.analyze_video --sample 3
"""
from typing import Optional

import typer
from sqlalchemy import select

from creative_director.advice.benchmark import compute_benchmark
from creative_director.advice.breakdown import analyze_video, format_breakdown
from creative_director.advice.timeline_benchmark import (
    analyze_timeline,
    compute_timeline_benchmark,
    format_frame_breakdown,
)
from creative_director.advice.narrate import NarrationError, narrate_breakdown
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video, VideoLabel


app = typer.Typer(add_completion=False)


@app.command()
def main(
    video_id: Optional[str] = typer.Option(None, help="A specific video ID"),
    sample: int = typer.Option(0, help="Instead, analyze N sample videos (mix of terciles)"),
    narrate: bool = typer.Option(False, help="Also generate the LLM creative-director note"),
):
    benchmark = compute_benchmark()
    frame_benchmark = compute_timeline_benchmark()
    print(
        f"Benchmark: {benchmark['niche']} / {benchmark['label_scheme']} "
        f"/ {benchmark['n_total']} labeled videos\n"
    )

    ids: list[str] = []
    if video_id:
        ids = [video_id]
    elif sample > 0:
        # pick a spread across terciles
        with session_scope() as s:
            for t in (2, 1, 0):
                rows = s.execute(
                    select(VideoLabel.video_id)
                    .where(VideoLabel.label_scheme == benchmark["label_scheme"])
                    .where(VideoLabel.tercile == t)
                    .limit(max(1, sample // 3 + 1))
                ).scalars().all()
                ids.extend(rows)
        ids = ids[:sample]
    else:
        raise typer.BadParameter("Pass --video-id or --sample N")

    for vid in ids:
        try:
            b = analyze_video(vid, benchmark=benchmark)
            print(format_breakdown(b))
            print()
            fb = analyze_timeline(vid, benchmark=frame_benchmark)
            print(format_frame_breakdown(fb))
            if narrate:
                print()
                print("CREATIVE-DIRECTOR NOTE:")
                try:
                    print(narrate_breakdown(b, fb))
                except NarrationError as e:
                    print(f"  (narration unavailable: {e})")
            print("-" * 70)
        except Exception as e:
            print(f"{vid}: FAILED — {e}")


if __name__ == "__main__":
    app()
