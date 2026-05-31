"""Backfill engagement-prompt features for every reel that has features."""
from __future__ import annotations

from sqlalchemy import select

from creative_director.features.engagement_prompts import extract_for_features
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video, VideoFeatures


def main() -> None:
    BATCH = 500
    with session_scope() as s:
        ids = [
            r[0]
            for r in s.execute(select(VideoFeatures.video_id)).all()
        ]
    print(f"Backfilling engagement prompts for {len(ids)} rows ...")
    written = 0
    counts = {
        "save": 0,
        "tag": 0,
        "follow": 0,
        "comment": 0,
        "question": 0,
    }
    for i in range(0, len(ids), BATCH):
        chunk = ids[i : i + BATCH]
        with session_scope() as s:
            rows = s.execute(
                select(Video, VideoFeatures).join(
                    VideoFeatures, VideoFeatures.video_id == Video.id
                ).where(Video.id.in_(chunk))
            ).all()
            for video, feat in rows:
                d = extract_for_features(
                    title=video.title,
                    description=video.description,
                    transcript=feat.transcript,
                    transcript_first_3s=feat.transcript_first_3s,
                )
                feat.engagement_has_save_prompt = d["engagement_has_save_prompt"]
                feat.engagement_has_tag_prompt = d["engagement_has_tag_prompt"]
                feat.engagement_has_follow_prompt = d["engagement_has_follow_prompt"]
                feat.engagement_has_comment_prompt = d["engagement_has_comment_prompt"]
                feat.engagement_has_question_hook = d["engagement_has_question_hook"]
                feat.engagement_prompt_count = d["engagement_prompt_count"]
                counts["save"] += d["engagement_has_save_prompt"]
                counts["tag"] += d["engagement_has_tag_prompt"]
                counts["follow"] += d["engagement_has_follow_prompt"]
                counts["comment"] += d["engagement_has_comment_prompt"]
                counts["question"] += d["engagement_has_question_hook"]
                written += 1
        print(f"  ...{written}/{len(ids)}")
    print(f"Done. Wrote {written} rows.")
    print(f"Hit counts (across all reels):")
    for k, v in counts.items():
        print(f"  {k:<10} {v:>5}  ({100*v/max(1, written):.1f}%)")


if __name__ == "__main__":
    main()
