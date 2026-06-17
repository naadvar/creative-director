"""Finer craft-move discriminativeness test (winners vs non-winners), to confirm
whether ANY sharper craft move predicts cross-channel performance before we
commit to an honest-craft framing. Same winner label as the app (views_per_sub_aged_v1).
"""
from __future__ import annotations

import re
import statistics as st
from collections import defaultdict

from sqlalchemy import select

from api.config import api_settings
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel

MIN_LIFT = 0.12
SCHEME = api_settings.label_scheme

_HOOK = re.compile(r"\?|\bhow (to|i|she|he|they)\b|\bwhy\b|\d|\byou\b|\byour\b|\bstop\b|\bnever\b|"
                   r"secret|mistake|\bthis\b|watch|wait|\bbest\b|\bworst\b|\bvs\b", re.I)
_NOTHOOK = re.compile(r"^[@#][\w.]+$")  # bare handle/hashtag
_TEXTCARD_OPEN = re.compile(r"text card|title (card|slate|screen|sequence)|intro card|logo bump|"
                            r"\bslate\b|black frame|blank frame|empty frame|wasted|just text|only text|no subject", re.I)


def fine_moves(p, dur, words, band, wmed):
    """Return {move_id: True/False/None} for one reel."""
    out = {}
    ost = (p.get("opening_shot") or "").strip()
    t = p.get("on_screen_text")
    tt = str(t).strip() if t is not None else None

    # 1. on-screen text is a real HOOK line (question/number/you/curiosity), not a watermark
    if tt is None:
        out["text_hook_style"] = None
    elif not tt or _NOTHOOK.match(tt) or len(tt.split()) < 2:
        out["text_hook_style"] = False
    else:
        out["text_hook_style"] = bool(_HOOK.search(tt))

    # 2. on-screen text is a substantive line (not a bare handle/watermark)
    if tt is None:
        out["substantive_text"] = None
    else:
        out["substantive_text"] = bool(tt) and not _NOTHOOK.match(tt) and len(tt.split()) >= 2

    # 3. opens on a subject/scene, NOT a text card / slate / logo / empty frame
    out["opens_not_textcard"] = (not bool(_TEXTCARD_OPEN.search(ost))) if ost else None

    # 4. duration inside the winner band [p25, p75] for the niche
    out["tight_duration"] = (band[0] <= dur <= band[1]) if (dur and band) else None

    # 5. concise script: talking reels only (words>=15), words <= winner median
    if words is None or words < 15 or wmed is None:
        out["concise_script"] = None
    else:
        out["concise_script"] = words <= wmed

    return out


def main():
    with session_scope() as s:
        rows = s.execute(
            select(Channel.niche, VideoLabel.tercile, VideoFeatures.vlm_perception,
                   Video.duration_seconds, VideoFeatures.transcript_word_count)
            .join(Video, Video.id == VideoFeatures.video_id)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoLabel, (VideoLabel.video_id == VideoFeatures.video_id) & (VideoLabel.label_scheme == SCHEME))
            .where(VideoFeatures.vlm_perception.isnot(None))
        ).all()
    print(f"scheme={SCHEME} rows={len(rows)}\n")

    # winner (tercile-2) duration band + script median, per niche
    durs = defaultdict(list); wds = defaultdict(list)
    for niche, terc, perc, dur, words in rows:
        if terc == 2 and niche:
            if dur: durs[niche].append(dur)
            if words and words >= 15: wds[niche].append(words)
    band = {n: (st.quantiles(v, n=4)[0], st.quantiles(v, n=4)[2]) for n, v in durs.items() if len(v) >= 8}
    wmed = {n: st.median(v) for n, v in wds.items() if len(v) >= 8}

    tallies = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    for niche, terc, perc, dur, words in rows:
        if niche is None or terc not in (0, 2) or not isinstance(perc, dict):
            continue
        mv = fine_moves(perc, dur, words, band.get(niche), wmed.get(niche))
        for mid, val in mv.items():
            if val is None:
                continue
            tallies[niche][mid][terc][1] += 1
            if val:
                tallies[niche][mid][terc][0] += 1

    mids = ["text_hook_style", "substantive_text", "opens_not_textcard", "tight_duration", "concise_script"]
    hits = 0
    for niche in sorted(tallies):
        print(f"=== {niche}  (dur band={band.get(niche)}, script med={wmed.get(niche)}) ===")
        for mid in mids:
            win = tallies[niche][mid][2]; bot = tallies[niche][mid][0]
            wr = win[0]/win[1] if win[1] else None
            br = bot[0]/bot[1] if bot[1] else None
            disc = wr is not None and br is not None and (wr-br) >= MIN_LIFT and wr >= 0.40
            if disc: hits += 1
            wr_s = f"{wr:.2f}" if wr is not None else "  - "
            br_s = f"{br:.2f}" if br is not None else "  - "
            lift = f"{wr-br:+.2f}" if (wr is not None and br is not None) else "  -  "
            print(f"  {'KEEP' if disc else '    '}  {mid:18} win={wr_s}(n={win[1]:4}) bot={br_s}(n={bot[1]:4}) lift={lift}")
        print()
    print(f"discriminative cells: {hits}")


if __name__ == "__main__":
    main()
