"""Verify a downloaded DB: integrity + Wave 2 / embedding coverage."""
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "creative_director_v3_pod.db"
c = sqlite3.connect(db)
print(f"DB: {db}")
print("integrity:", c.execute("PRAGMA integrity_check").fetchone()[0])


def n(col):
    return c.execute(
        f"SELECT COUNT(1) FROM video_features WHERE {col} IS NOT NULL"
    ).fetchone()[0]


for col in (
    "description_embedding",
    "hook_face_present_frac",
    "hook_emotion_surprised",
    "hook_clip_image_embedding",
    "music_uses_original",
    "topic_cluster_id",
):
    print(f"  {col:28} {n(col)}")
print("total feature rows:", c.execute("SELECT COUNT(1) FROM video_features").fetchone()[0])
