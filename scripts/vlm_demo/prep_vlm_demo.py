"""Prep for the 'what would a VLM give us' demo.

Selects a low/mid-weighted, multi-niche sample of REAL reels, dumps what the
CURRENT scalar system says about each, plus the hook context, and extracts a
real opening-frame strip (from the R2 mp4, falling back to the local thumbnail)
so a vision model can actually look at the hook. Writes:
  data/tmp/vlm_demo_context.json   (per-reel context for the critique agents)
  data/tmp/vlm_frames/<vid>.jpg    (opening-frame strip or thumbnail)
"""
import json
import os
import tempfile
from pathlib import Path

import cv2

from api.benchmarks import benchmarks, pick_for_tier
from creative_director.advice.breakdown import analyze_video
from creative_director.advice.summary import build_summary
from creative_director.advice.tier import tier_for_count
from creative_director.storage import media
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel
from sqlalchemy import select, desc, asc

LABEL = "views_per_sub_aged_v1"
OUTDIR = Path("data/tmp/vlm_frames")
OUTDIR.mkdir(parents=True, exist_ok=True)

# Weighted toward LOW/MID (where the user says suggestions are iffy), a couple
# of niches for breadth, plus the two pathological fitness cases by name.
PLAN = [
    ("ig_fitness", "named", "ig_DWBmcPjMNd3"),  # -10.0 but "no gaps stand out"
    ("ig_fitness", "named", "ig_DW9UOZls0PS"),  # -9.3 "open on exercise demo"
    ("ig_fitness", "top", None),                # +contrast
    ("ig_food", "low", None),
    ("ig_food", "mid", None),
    ("ig_travel", "low", None),
    ("ig_travel", "mid", None),
    ("ig_fashion", "low", None),
]

_TNAME = {0: "low", 1: "mid", 2: "high"}


def ranked(niche):
    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Channel.subscriber_count, VideoLabel.score, VideoLabel.tercile)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(VideoLabel, VideoLabel.video_id == Video.id)
            .where(Channel.niche == niche, VideoLabel.label_scheme == LABEL)
            .order_by(desc(VideoLabel.score))
        ).all()
    return rows


def pick(niche, kind, named):
    rows = ranked(niche)
    if kind == "named":
        for r in rows:
            if r[0] == named:
                return r
        return None
    if kind == "top":
        return rows[0]
    if kind == "low":
        return rows[-1]
    if kind == "mid":
        return rows[len(rows) // 2]


def extract_strip(vid):
    """Pull the mp4 from R2, write a 4-frame opening strip. Fallback: thumbnail."""
    out = OUTDIR / f"{vid}.jpg"
    try:
        from creative_director.config import settings
        cl = media._client()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
            tmp = tf.name
        cl.download_file(settings.r2_bucket, media.video_key(vid), tmp)
        cap = cv2.VideoCapture(tmp)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frames = []
        for t in (0.0, 0.8, 1.6, 2.6):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, fr = cap.read()
            if ok:
                h = 360
                w = int(fr.shape[1] * h / fr.shape[0])
                frames.append(cv2.resize(fr, (w, h)))
        cap.release()
        os.unlink(tmp)
        if frames:
            strip = cv2.hconcat(frames)
            cv2.imwrite(str(out), strip)
            return str(out), f"{len(frames)}-frame opening strip (0.0/0.8/1.6/2.6s)"
    except Exception as e:  # noqa: BLE001
        print(f"  [r2 mp4 failed for {vid}: {str(e)[:80]}]")
    # fallback: local thumbnail (single first frame ~0.5s)
    thumb = Path("data/thumbnails") / f"{vid}.jpg"
    if thumb.exists():
        img = cv2.imread(str(thumb))
        if img is not None:
            cv2.imwrite(str(out), img)
            return str(out), "single opening frame (~0.5s, local thumbnail; mp4 not on R2)"
    return None, "NO FRAME AVAILABLE"


def winner_ctx(niche, tier, arch):
    tl = benchmarks.timeline(niche)
    bm, _ = pick_for_tier(tl, tier, arch)
    ab = (bm.get("archetypes") or {}).get(arch, {})
    vibes = ab.get("hook_vibe_dist") or {}
    top_vibes = {k: round(v, 2) for k, v in list(vibes.items())[:4]}
    return {
        "winner_top_hook_openers": top_vibes,
        "winner_hook_face_frac": round(ab.get("hook_face_frac"), 2) if ab.get("hook_face_frac") is not None else None,
        "winner_first_cut_s": ab.get("first_cut_second_median"),
        "winner_n": ab.get("n_winners"),
    }


def fnum(v, n=2):
    return round(float(v), n) if v is not None else None


out = []
for niche, kind, named in PLAN:
    r = pick(niche, kind, named)
    if not r:
        print(f"skip {niche}/{kind}/{named}: not found")
        continue
    vid, subs, score, tercile = r
    tier = tier_for_count(subs)
    bd = analyze_video(vid, benchmarks_by_tier=benchmarks.aggregate(niche))
    arch = bd.archetype
    tl_bm, _ = pick_for_tier(benchmarks.timeline(niche), tier, arch)
    plain = build_summary(bd, tl_bm, niche)
    f = bd  # features via session
    with session_scope() as s:
        vf = s.get(VideoFeatures, vid) or s.execute(select(VideoFeatures).where(VideoFeatures.video_id == vid)).scalar_one_or_none()
        title = (s.get(Video, vid).title or "")[:120]
    frame_path, frame_desc = extract_strip(vid)
    ctx = {
        "video_id": vid,
        "niche": niche,
        "tier": tier,
        "archetype": arch,
        "perf_label": round(score, 2),
        "perf_tercile": _TNAME.get(tercile),
        "duration_s": bd.duration_seconds,
        "frame_image": frame_path,
        "frame_desc": frame_desc,
        "title_or_caption_opening": title,
        "CURRENT_SYSTEM_OUTPUT": {
            "read": plain.read,
            "worth_trying": [w.text for w in plain.worth_trying],
            "rec_card": [rr["advice"] for rr in (bd.recommendations or [])],
        },
        "hook_signals_we_already_have": {
            "transcript_first_3s": (getattr(vf, "transcript_first_3s", None) or "")[:200],
            "emotion_happy": fnum(getattr(vf, "hook_emotion_happy", None)),
            "emotion_intense": fnum(getattr(vf, "hook_emotion_intense", None)),
            "emotion_surprised": fnum(getattr(vf, "hook_emotion_surprised", None)),
            "emotion_neutral": fnum(getattr(vf, "hook_emotion_neutral", None)),
            "hook_face_present_frac": fnum(getattr(vf, "hook_face_present_frac", None)),
            "is_action_first": getattr(vf, "hook_is_action_first", None),
            "first3s_text_present": getattr(vf, "first3s_text_present", None),
            "first3s_motion_intensity": fnum(getattr(vf, "first3s_motion_intensity", None)),
        },
        "winner_context_for_this_cohort": winner_ctx(niche, tier, arch),
    }
    out.append(ctx)
    print(f"OK {vid} {niche} {kind} perf={score:+.2f} frame={frame_desc}")

with open("data/tmp/vlm_demo_context.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2)
print(f"\nwrote data/tmp/vlm_demo_context.json with {len(out)} reels")
