"""CLI: compute virality labels for all videos in the DB.

Examples
--------
    python -m scripts.compute_labels
    python -m scripts.compute_labels --niche fitness
"""
from typing import Optional

import typer
from loguru import logger

from creative_director.labels.compute import compute_all_labels
from creative_director.storage.db import init_db, session_scope


app = typer.Typer(add_completion=False)


@app.command()
def main(
    niche: Optional[str] = typer.Option(None, help="Scope to a single niche; default = all"),
):
    init_db()
    with session_scope() as s:
        stats = compute_all_labels(s, niche=niche)
    logger.info(f"Done: {stats}")


if __name__ == "__main__":
    app()
