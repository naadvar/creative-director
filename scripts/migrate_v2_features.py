"""Additive schema migration for the v2 feature work.

Adds columns to ``video_features`` for the 5 new feature families
(engagement prompts, hook text embedding + flags, hook audio fingerprint,
topic cluster id, music metadata). Idempotent -- skips columns that
already exist. SQLite-only (uses ALTER TABLE ADD COLUMN).

Run before any of the new backfills.
"""
from __future__ import annotations

import sqlite3

from creative_director.config import settings


_NEW_COLUMNS: list[tuple[str, str]] = [
    # --- Engagement prompts (computed on text fields, stored for SHAP visibility) ---
    ("engagement_has_save_prompt", "INTEGER"),
    ("engagement_has_tag_prompt", "INTEGER"),
    ("engagement_has_follow_prompt", "INTEGER"),
    ("engagement_has_comment_prompt", "INTEGER"),
    ("engagement_has_question_hook", "INTEGER"),
    ("engagement_prompt_count", "INTEGER"),

    # --- Hook text (first-3s transcript) ---
    ("hook_text_embedding", "TEXT"),  # JSON 384-dim list from SentenceTransformer
    ("hook_starts_with_question", "INTEGER"),
    ("hook_uses_you", "INTEGER"),
    ("hook_uses_number", "INTEGER"),
    ("hook_has_negation", "INTEGER"),
    ("hook_word_count", "INTEGER"),

    # --- Hook audio fingerprint (first 1-2s of audio waveform) ---
    ("hook_audio_peak_loudness", "REAL"),
    ("hook_audio_mean_loudness", "REAL"),
    ("hook_audio_attack_rate", "REAL"),
    ("hook_audio_is_voice", "INTEGER"),

    # --- Topic subcluster id (offline k-means per niche over thumb+title PCA) ---
    ("topic_cluster_id", "INTEGER"),

    # --- Music metadata (IG only; NULL for YT) ---
    ("music_uses_original", "INTEGER"),
    ("music_audio_id", "TEXT"),
    ("music_audio_id_corpus_uses", "INTEGER"),

    # --- v3: description embedding (SentenceTransformer 384d, JSON) ---
    ("description_embedding", "TEXT"),

    # --- Wave 2: visual frame features (from mp4 via hook_visual.py) ---
    ("hook_face_fill", "REAL"),
    ("hook_face_headroom", "REAL"),
    ("hook_frontal_ratio", "REAL"),
    ("hook_face_present_frac", "REAL"),
    ("hook_background_clutter", "REAL"),
    ("hook_is_action_first", "INTEGER"),
    ("hook_motion_first", "REAL"),
    ("hook_emotion_happy", "REAL"),
    ("hook_emotion_intense", "REAL"),
    ("hook_emotion_surprised", "REAL"),
    ("hook_emotion_neutral", "REAL"),
    ("hook_clip_image_embedding", "TEXT"),  # 512d CLIP image embedding, JSON
]


def _existing_columns(con: sqlite3.Connection, table: str) -> set[str]:
    cur = con.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def main() -> None:
    db_path = str(settings.database_url).replace("sqlite:///", "")
    if db_path.startswith("/"):
        # sqlite:////absolute/path uses 4 slashes; the URL above leaves a leading /
        # on POSIX. On Windows the standard form `sqlite:///C:/...` works as-is.
        pass
    print(f"Migrating: {db_path}")
    con = sqlite3.connect(db_path)
    existing = _existing_columns(con, "video_features")
    added = 0
    skipped = 0
    for name, sqltype in _NEW_COLUMNS:
        if name in existing:
            skipped += 1
            continue
        con.execute(f"ALTER TABLE video_features ADD COLUMN {name} {sqltype}")
        added += 1
        print(f"  + {name} {sqltype}")
    con.commit()
    con.close()
    print(f"Done. added={added}, skipped={skipped}")


if __name__ == "__main__":
    main()
