"""CLI: merge Colab-extracted features back into the live local DB.

The Colab run writes VideoFeatures + VideoTimeline into a copy of the DB. The
local DB meanwhile keeps changing (the velocity cron appends snapshots), so we
cannot just swap files — this copies only the new VideoFeatures / VideoTimeline
rows across.

Idempotent: only rows missing from the target are added.

    python -m scripts.merge_features --source data/creative_director_processed.db
"""
import sqlite3
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(add_completion=False)


@app.command()
def main(
    source: Path = typer.Option(..., help="Colab-processed DB (creative_director_processed.db)"),
    target: Path = typer.Option(
        Path("data/creative_director.db"), help="Live local DB to merge into"
    ),
    dry_run: bool = typer.Option(False, help="Report what would be merged, write nothing"),
):
    if not source.exists():
        raise FileNotFoundError(f"Source DB not found: {source}")
    if not target.exists():
        raise FileNotFoundError(f"Target DB not found: {target}")

    src = sqlite3.connect(source)
    tgt = sqlite3.connect(target)

    # --- VideoFeatures: copy rows for video_ids the target lacks ---
    src_feat = {r[0] for r in src.execute("select video_id from video_features")}
    tgt_feat = {r[0] for r in tgt.execute("select video_id from video_features")}
    new_feat = sorted(src_feat - tgt_feat)

    feat_cols = [r[1] for r in src.execute("pragma table_info(video_features)")]
    fcols = ",".join(feat_cols)
    fph = ",".join("?" * len(feat_cols))

    # --- VideoTimeline: copy rows for video_ids the target has no timeline for ---
    tl_cols = [r[1] for r in src.execute("pragma table_info(video_timeline)") if r[1] != "id"]
    tcols = ",".join(tl_cols)
    tph = ",".join("?" * len(tl_cols))
    src_tl_vids = {r[0] for r in src.execute("select distinct video_id from video_timeline")}
    tgt_tl_vids = {r[0] for r in tgt.execute("select distinct video_id from video_timeline")}
    new_tl_vids = sorted(src_tl_vids - tgt_tl_vids)

    n_tl_rows = 0
    for vid in new_tl_vids:
        n_tl_rows += src.execute(
            "select count(*) from video_timeline where video_id=?", (vid,)
        ).fetchone()[0]

    logger.info(
        f"To merge: {len(new_feat)} VideoFeatures rows, "
        f"{n_tl_rows} VideoTimeline rows across {len(new_tl_vids)} videos"
    )

    if dry_run:
        logger.info("Dry run — nothing written.")
        return

    for vid in new_feat:
        row = src.execute(
            f"select {fcols} from video_features where video_id=?", (vid,)
        ).fetchone()
        tgt.execute(
            f"insert or replace into video_features ({fcols}) values ({fph})", row
        )

    written_tl = 0
    for vid in new_tl_vids:
        for row in src.execute(
            f"select {tcols} from video_timeline where video_id=?", (vid,)
        ):
            tgt.execute(
                f"insert into video_timeline ({tcols}) values ({tph})", row
            )
            written_tl += 1

    tgt.commit()
    src.close()
    tgt.close()
    logger.info(f"Merged {len(new_feat)} VideoFeatures + {written_tl} VideoTimeline rows.")


if __name__ == "__main__":
    app()
