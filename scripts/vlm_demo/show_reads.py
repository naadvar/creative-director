"""Show the grounded read on real rich-tagged corpus reels (2 per niche)."""
from collections import defaultdict

from sqlalchemy import select

from api.benchmarks import benchmarks, pick_for_tier
from creative_director.advice.benchmark import classify_archetype
from creative_director.advice.breakdown import analyze_video
from creative_director.advice.summary import build_summary
from creative_director.advice.tier import tier_for_count
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures

with session_scope() as s:
    rows = s.execute(
        select(Video.id, Channel.niche, Channel.subscriber_count,
               VideoFeatures.transcript_word_count, Video.duration_seconds,
               VideoFeatures.vlm_perception)
        .join(Channel, Channel.id == Video.channel_id)
        .join(VideoFeatures, VideoFeatures.video_id == Video.id)
        .where(Channel.id.notlike("upch_%"))
    ).all()

# keep only rich-tagged (has opening_shot), 2 per niche
per = defaultdict(list)
for vid, niche, subs, words, dur, vp in rows:
    if isinstance(vp, dict) and vp.get("opening_shot") and len(per[niche]) < 2:
        per[niche].append((vid, niche, subs, words, dur, vp))

for niche, items in per.items():
    for vid, niche, subs, words, dur, vp in items:
        tier = tier_for_count(subs)
        arch = classify_archetype(words)
        bd = analyze_video(vid, benchmarks_by_tier=benchmarks.aggregate(niche))
        tl_bm, _ = pick_for_tier(benchmarks.timeline(niche), tier, arch)
        plain = build_summary(bd, tl_bm, niche)
        print(f"\n=== [{niche}] {vid}  tier={tier} arch={arch} tercile={bd.tercile} ===")
        print(f"  opening_shot (raw): {(vp.get('opening_shot') or '')[:160]}")
        print(f"  READ: {plain.read}")
        if plain.worth_trying:
            print(f"  WORTH TRYING: {plain.worth_trying[0].text}")
