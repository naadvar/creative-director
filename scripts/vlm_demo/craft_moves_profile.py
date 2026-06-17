"""Profile the craft moves over the corpus: per niche, how often do WINNERS
(tercile 2) have each move vs NON-winners (tercile 0)? Keep only moves that
separate them (the discriminativeness gate). Writes data/advice/craft_moves_profile.json
+ prints a readable table. No model, no new pass — reads the rich perception in the DB.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import func, select

from api.config import api_settings
from creative_director.advice.craft_moves import MOVES, MOVE_LABEL, moves_for
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel

MIN_LIFT = 0.12      # winner_rate - bottom_rate to call a move discriminative
MIN_WINNER = 0.40    # winners must actually do it this often
OUT = Path("data/advice/craft_moves_profile.json")


def _best_scheme(s) -> str:
    """The label scheme with the most tercile-2 reels that also have rich perception."""
    rows = s.execute(
        select(VideoLabel.label_scheme, func.count())
        .join(VideoFeatures, VideoFeatures.video_id == VideoLabel.video_id)
        .where(VideoLabel.tercile == 2, VideoFeatures.vlm_perception.isnot(None))
        .group_by(VideoLabel.label_scheme)
    ).all()
    rows.sort(key=lambda r: -r[1])
    print("label schemes (tercile-2 reels w/ perception):", {k: v for k, v in rows})
    return rows[0][0]


def main():
    with session_scope() as s:
        _best_scheme(s)  # diagnostic only
        # Winners = the app's honest cross-channel label (NOT the within-channel
        # per_channel label, which the model gate showed is ~random). Same scheme
        # find_examples uses, so craft-move winners == the winners we retrieve.
        scheme = api_settings.label_scheme
        rows = s.execute(
            select(Channel.niche, VideoLabel.tercile, VideoFeatures.vlm_perception)
            .join(Video, Video.id == VideoFeatures.video_id)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoLabel, (VideoLabel.video_id == VideoFeatures.video_id)
                  & (VideoLabel.label_scheme == scheme))
            .where(VideoFeatures.vlm_perception.isnot(None))
        ).all()
        # collect exemplar ids (tercile-2, move present) per (niche, move)
        ex_rows = s.execute(
            select(Channel.niche, VideoFeatures.video_id, VideoFeatures.vlm_perception)
            .join(Video, Video.id == VideoFeatures.video_id)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoLabel, (VideoLabel.video_id == VideoFeatures.video_id)
                  & (VideoLabel.label_scheme == scheme))
            .where(VideoFeatures.vlm_perception.isnot(None), VideoLabel.tercile == 2)
        ).all()

    print(f"scheme={scheme}  rows={len(rows)}\n")
    # tallies[niche][move][tercile] = [n_true, n_determinable]
    tallies = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    for niche, terc, perc in rows:
        if niche is None or terc not in (0, 2):
            continue
        mv = moves_for(perc)
        for mid, val in mv.items():
            if val is None:
                continue
            tallies[niche][mid][terc][1] += 1
            if val:
                tallies[niche][mid][terc][0] += 1

    exemplars = defaultdict(lambda: defaultdict(list))
    for niche, vid, perc in ex_rows:
        if niche is None:
            continue
        for mid, val in moves_for(perc).items():
            if val and len(exemplars[niche][mid]) < 25:
                exemplars[niche][mid].append(vid)

    profile = {}
    for niche in sorted(tallies):
        print(f"=== {niche} ===")
        profile[niche] = {}
        for mid, _label, _ in MOVES:
            win = tallies[niche][mid][2]
            bot = tallies[niche][mid][0]
            wr = win[0] / win[1] if win[1] else None
            br = bot[0] / bot[1] if bot[1] else None
            disc = (wr is not None and br is not None and (wr - br) >= MIN_LIFT and wr >= MIN_WINNER)
            profile[niche][mid] = {
                "label": MOVE_LABEL[mid], "winner_rate": wr, "bottom_rate": br,
                "n_win": win[1], "n_bot": bot[1], "discriminative": disc,
                "exemplars": exemplars[niche][mid],
            }
            wr_s = f"{wr:.2f}" if wr is not None else "  - "
            br_s = f"{br:.2f}" if br is not None else "  - "
            lift = f"{wr-br:+.2f}" if (wr is not None and br is not None) else "  -  "
            print(f"  {'KEEP' if disc else '    '}  {mid:20} win={wr_s} (n={win[1]:4})  bot={br_s} (n={bot[1]:4})  lift={lift}")
        print()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    kept = sum(1 for n in profile.values() for m in n.values() if m["discriminative"])
    print(f"wrote {OUT}  ({kept} discriminative niche×move cells kept)")


if __name__ == "__main__":
    main()
