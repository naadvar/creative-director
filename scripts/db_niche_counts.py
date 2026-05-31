"""Video counts per niche in the live DB (total vs analyzable/with-features).

    python -m scripts.db_niche_counts
"""
from sqlalchemy import func, select

from creative_director.config import settings
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel


def main() -> None:
    print(f"DB: {settings.database_url}\n")
    with session_scope() as s:
        totals = dict(
            s.execute(
                select(Channel.niche, func.count(Video.id))
                .join(Channel, Channel.id == Video.channel_id)
                .group_by(Channel.niche)
            ).all()
        )
        feats = dict(
            s.execute(
                select(Channel.niche, func.count(Video.id))
                .join(Channel, Channel.id == Video.channel_id)
                .join(VideoFeatures, VideoFeatures.video_id == Video.id)
                .group_by(Channel.niche)
            ).all()
        )
        labels = dict(
            s.execute(
                select(Channel.niche, func.count(Video.id))
                .join(Channel, Channel.id == Video.channel_id)
                .join(VideoLabel, VideoLabel.video_id == Video.id)
                .group_by(Channel.niche)
            ).all()
        )

    print(f"{'niche':<22}{'videos':>9}{'features':>10}{'labels':>9}")
    print("-" * 50)
    for niche, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"{(niche or '(none)'):<22}{n:>9}{feats.get(niche, 0):>10}{labels.get(niche, 0):>9}")


if __name__ == "__main__":
    main()
