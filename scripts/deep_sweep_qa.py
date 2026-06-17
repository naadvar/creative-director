"""Deep QA sweep: run the FULL advice surface for EVERY analyzable video and
machine-check it for absurdity/contradiction classes. Writes a report with
per-detector counts + worst examples, plus a random eyeball sample.

    python -m scripts.deep_sweep_qa                  # all videos
    python -m scripts.deep_sweep_qa --limit 200      # quick pass
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

import typer
from loguru import logger
from sqlalchemy import select

from api.benchmarks import benchmarks, pick_for_tier
from creative_director.advice.benchmark import classify_archetype, face_advice_applies, is_voiceover_led
from creative_director.advice.breakdown import analyze_video
from creative_director.advice.cutplan import build_auto_cut, build_cut_plan
from creative_director.advice.summary import build_summary
from creative_director.advice.tier import tier_for_count
from creative_director.advice.timeline_benchmark import analyze_timeline
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoTimeline

app = typer.Typer(add_completion=False)
OUT = "data/tmp/deep_sweep.txt"
OUT_JSON = "data/tmp/deep_sweep_flags.json"

_NUM_VS = re.compile(r"(\d+(?:\.\d+)?) vs about (\d+(?:\.\d+)?) for winners")


def main_query():
    with session_scope() as s:
        rows = s.execute(
            select(
                Video.id,
                Channel.niche,
                Channel.subscriber_count,
                VideoFeatures.transcript_word_count,
                Video.duration_seconds,
            )
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(VideoTimeline, VideoTimeline.video_id == Video.id)
            .where(Channel.id.notlike("upch_%"))
            .distinct()
        ).all()
    return rows


def face_frac_for(video_id: str):
    with session_scope() as s:
        rows = s.execute(
            select(VideoTimeline.has_face).where(VideoTimeline.video_id == video_id)
        ).all()
    vals = [r[0] for r in rows if r[0] is not None]
    return (sum(vals) / len(vals)) if vals else None


@app.command()
def main(limit: int = typer.Option(0, help="Max videos (0 = all)")) -> None:
    rows = main_query()
    rows.sort(key=lambda r: r[0])
    if limit:
        rows = rows[:limit]
    logger.info(f"deep sweep over {len(rows)} videos")

    flags: dict[str, list] = defaultdict(list)
    stats: Counter = Counter()
    sample_dump: list[str] = []

    def flag(kind: str, vid: str, detail: str):
        stats[kind] += 1
        if len(flags[kind]) < 8:
            flags[kind].append(f"{vid}: {detail}")

    for i, (vid, niche, subs, words, dur) in enumerate(rows):
        if i % 500 == 0:
            logger.info(f"[{i}/{len(rows)}]")
        try:
            tier = tier_for_count(subs)
            arch = classify_archetype(words)
            ff = face_frac_for(vid)
            fa = face_advice_applies(arch, ff)
            vo = is_voiceover_led(arch, ff)
            stats["videos"] += 1
            if vo:
                stats["voiceover_led_videos"] += 1
            if not fa:
                stats["no_presenter_videos"] += 1

            # --- breakdown (findings + pattern + recommendations) ---
            bd = analyze_video(vid, benchmarks_by_tier=benchmarks.aggregate(niche))
            recs = bd.recommendations or []
            for r in recs:
                if r.get("feature") == "first3s_face_present" and not fa and "Show a face" in r.get("advice", ""):
                    flag("REC_face_on_no_presenter", vid, r["advice"])
                if r.get("feature") == "audio_voice_ratio" and arch == "demo" and (words or 0) < 5 and "voiceover" in r.get("advice", "").lower() and r.get("advice", "").startswith("Add"):
                    flag("REC_add_voice_on_silent", vid, r["advice"])
                if r.get("winner_value") is not None and r.get("your_value") == r.get("winner_value"):
                    flag("REC_your_equals_winner", vid, f"{r['feature']} {r['your_value']}")

            # --- summary (read + worth_trying) ---
            tl_bm, _ = pick_for_tier(benchmarks.timeline(niche), tier, arch)
            plain = build_summary(bd, tl_bm, niche)
            texts = [w.text for w in plain.worth_trying]
            blob = plain.read + " " + " ".join(texts)
            if not fa and ("face on screen" in blob.lower()):
                flag("SUMMARY_face_on_no_presenter", vid, blob[:140])
            for t in texts:
                m = _NUM_VS.search(t)
                if m and "emoji" in t and abs(float(m.group(1)) - float(m.group(2))) < 2:
                    flag("TINY_emoji_gap", vid, t)
                if m and "spoken words" in t and abs(float(m.group(1)) - float(m.group(2))) < 15:
                    flag("TINY_word_gap", vid, t)
                if "weak signal" in t:
                    flag("PROXY_in_worth", vid, t[:90])
                if arch == "demo" and "Open on a person talking" in t:
                    flag("DEMO_told_open_talking", vid, t[:90])
            for r in recs:
                if (
                    r.get("feature") == "avg_shot_length"
                    and r.get("advice", "").startswith("Hold")
                    and dur
                    and (r.get("winner_value") or 0) > 0.8 * dur
                ):
                    flag("HOLD_longer_than_reel", vid, f"target {r.get('winner_value')}s on {dur}s reel")
            # duration direction conflict between read-suggestions and rec card
            sum_longer = any("runs short" in t for t in texts)
            sum_shorter = any("Tighten the length" in t for t in texts)
            rec_longer = any(r.get("feature") in ("duration_seconds",) and r.get("advice", "").lower().startswith("make it longer") for r in recs)
            rec_shorter = any(r.get("feature") in ("duration_seconds",) and r.get("advice", "").lower().startswith("make it shorter") for r in recs)
            if (sum_longer and rec_shorter) or (sum_shorter and rec_longer):
                flag("DURATION_conflict", vid, f"read_says={'short' if sum_longer else 'long'} rec_says={'shorter' if rec_shorter else 'longer'}")

            # --- cutplan + autocut ---
            from api.routers.videos import _cutplan_benchmark

            with session_scope() as s:
                cat = s.get(Video, vid).category
            cbm = _cutplan_benchmark(niche, tier, arch, cat)
            cp = build_cut_plan(vid, cbm)
            ac = build_auto_cut(vid, cbm)
            if vo:
                if cp and cp.get("suggested_trim_start"):
                    flag("VO_trim_suggested", vid, f"trim={cp['suggested_trim_start']}")
                if ac and ac.get("changed"):
                    flag("VO_autocut", vid, str(ac.get("removed")))
            if arch == "talking" and ac and ac.get("changed"):
                for rm in ac.get("removed") or []:
                    if rm["end"] >= (ac.get("original_duration") or 0) - 1 and rm["start"] > 0:
                        flag("TALKING_tail_cut", vid, str(rm))
            if cp and cp.get("benchmark_scope") == "category":
                n_win = (cbm.get("archetypes") or {}).get(arch, {}).get("n_winners")
                if n_win is not None and n_win < 8:
                    flag("THIN_category_benchmark", vid, f"cat={cat} n_winners={n_win}")

            # --- frame findings ---
            fb = analyze_timeline(vid, benchmark=tl_bm)
            for fnd in fb.findings:
                if not fa and "getting a face on screen" in fnd:
                    flag("FRAME_face_on_no_presenter", vid, fnd[:120])

            # --- copy stats ---
            # The YouTube-ism: ADVICE calling the caption a "title". IG advice uses
            # "caption opening", so this should be 0. The grounded opener legitimately
            # describes on-screen title text/cards ("a book titled X", "bold title 'Y'"),
            # which is correct — so match the YouTube-ism PHRASES, not the substring.
            if vid.startswith(("ig_", "up_")) and any(
                p in blob.lower() for p in
                ("the title", "your title", "shorten the title", "title runs",
                 "title length", "title emoji", "in the title", "title differs")
            ):
                stats["ig_reads_saying_title"] += 1
            if len(sample_dump) < 60 and i % max(1, len(rows) // 15) == 0:
                sample_dump.append(
                    f"\n### {vid} niche={niche} arch={arch} face={ff if ff is None else round(ff,2)} words={words} dur={dur}\n"
                    f"READ: {plain.read}\n" + "\n".join(f"  - {t}" for t in texts)
                    + "\nRECS: " + "; ".join(f"{r['advice']} (≈{r.get('winner_value')}, you {r.get('your_value')})" for r in recs[:4])
                )
        except Exception as e:  # noqa: BLE001
            flag("ERROR", vid, str(e)[:120])

    lines = [f"DEEP SWEEP — {stats['videos']} videos analyzed\n" + "=" * 70, "\nDETECTOR COUNTS:"]
    for k in sorted(stats):
        lines.append(f"  {k:32} {stats[k]}")
    lines.append("\nEXAMPLES PER DETECTOR:")
    for k, ex in sorted(flags.items()):
        lines.append(f"\n--- {k} ({stats[k]} total) ---")
        lines.extend(f"  {e}" for e in ex)
    lines.append("\n\nRANDOM EYEBALL SAMPLE:")
    lines.extend(sample_dump)

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in flags.items()}, fh, indent=1)
    logger.info(f"wrote {OUT}")
    print("SWEEP_DONE " + " ".join(f"{k}={stats[k]}" for k in sorted(stats) if k != "videos"))


if __name__ == "__main__":
    app()
