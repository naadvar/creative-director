"""Smoke-test the VLM perception module on real reels. Run once credits exist:

    python -m scripts.vlm_demo.smoke_perception

Uses cached dense strips from the earlier experiment when present, else pulls
the mp4 from R2 and samples fresh. Prints the canonical perception dict so you
can eyeball the grounded, cited tags before any of it is wired into advice.
"""
import json
import tempfile
from pathlib import Path

from creative_director.config import settings
from creative_director.features import vlm_perception as vp
from creative_director.storage import media

# (vid, niche, caption, duration) — a spread incl. the pathological demo cases.
REELS = [
    ("ig_DWBmcPjMNd3", "ig_fitness", "The spine works best when every section does its job.", 11),
    ("ig_DWBGNORjIQy", "ig_food", "4 Ingredients is Australia's #1 EASiEST Cookbooks.", 10),
    ("ig_DTiY-MyDX6q", "ig_fitness", "I think the beard suits me more anyway", 21),
]
CACHE = Path("data/tmp/vlm_frames_dense")


WORK = Path("data/tmp/vlm_smoke")


def strips_for(vid):
    cached = [CACHE / f"{vid}_{x}.jpg" for x in ("a", "b", "c")]
    if all(p.exists() for p in cached):
        # 12 frames @ dur*i/11 were stamped at extraction; reconstruct timestamps below per-reel
        return [str(p) for p in cached], None
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        mp4 = tf.name
    media._client().download_file(settings.r2_bucket, media.video_key(vid), mp4)
    # persistent dir (NOT a TemporaryDirectory — the strips must outlive this call)
    out = WORK / vid
    return vp.sample_strips(mp4, out)


if not settings.anthropic_api_key:
    raise SystemExit("No ANTHROPIC_API_KEY in .env")

for vid, niche, caption, dur in REELS:
    strips, ts = strips_for(vid)
    if ts is None:  # cached strips: 12 frames evenly across the clip
        ts = [round(dur * i / 11, 2) for i in range(12)]
    print(f"\n{'='*70}\n{vid}  ({niche}, {dur}s)  caption={caption!r}")
    tags = vp.perceive_from_strips(strips, niche=niche, caption=caption, duration_s=dur, timestamps=ts)
    if tags is None:
        print("  -> None (check credits / logs)")
        continue
    print(f"  genre={tags.get('genre')}  format={tags.get('format')}  "
          f"has_presenter={tags.get('has_presenter')}  confidence={tags.get('confidence')}")
    print(f"  opening_shot: {tags.get('opening_shot')}")
    print(f"  on_screen_text: {tags.get('on_screen_text')}")
    print(f"  observed ({len(tags.get('observed') or [])}, dropped={tags.get('observed_dropped')}):")
    for o in tags.get("observed") or []:
        print(f"     [{o['frame_ts']}s] {o['text']}")
    print("  hypothesis:")
    for h in tags.get("hypothesis") or []:
        print(f"     - {h['text']}")
