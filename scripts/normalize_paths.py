"""Normalize Windows backslash paths -> forward slashes in the DB so videos
ingested on Windows resolve on a Linux (pod) filesystem. Idempotent.

    python -m scripts.normalize_paths
"""
from sqlalchemy import text

from creative_director.storage.db import session_scope

_BS = chr(92)  # a single backslash, avoids escaping headaches


def main() -> None:
    with session_scope() as s:
        v = s.execute(
            text(
                f"UPDATE videos SET video_file_path = REPLACE(video_file_path, '{_BS}', '/') "
                f"WHERE video_file_path LIKE '%{_BS}%'"
            )
        ).rowcount
        t = s.execute(
            text(
                f"UPDATE videos SET thumbnail_path = REPLACE(thumbnail_path, '{_BS}', '/') "
                f"WHERE thumbnail_path LIKE '%{_BS}%'"
            )
        ).rowcount
        s.commit()
    print(f"normalized {v} video paths, {t} thumbnail paths")


if __name__ == "__main__":
    main()
