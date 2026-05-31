"""Creative Director — Streamlit frontend.

A validation/demo tool that wraps the existing advice layer:
  - Browse the ingested fitness-Shorts corpus and view each video's breakdown.
  - Paste any YouTube Shorts URL to ingest + analyze it on the fly.

The advice is correlational and pre-velocity-maturation — see the disclaimer
in the UI. Run from the project root:

    .venv/Scripts/python.exe -m streamlit run app.py
"""
from __future__ import annotations

import re

import streamlit as st
from sqlalchemy import select

from creative_director.advice.benchmark import compute_benchmark
from creative_director.advice.breakdown import analyze_video
from creative_director.advice.summary import ARCHETYPE_PLAIN, build_summary
from creative_director.advice.timeline_benchmark import (
    analyze_timeline,
    compute_per_second_benchmark,
    compute_timeline_benchmark,
    per_second_deviation,
)
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel

LABEL_SCHEME = "views_per_sub_aged_v1"
TERCILE = {0: ("Low performer", "#c0392b"), 1: ("Mid performer", "#7f8c8d"),
           2: ("High performer", "#27ae60")}

_YT_ID = re.compile(r"(?:shorts/|watch\?v=|youtu\.be/|/v/|embed/)([A-Za-z0-9_-]{11})")


def parse_video_id(text: str) -> str | None:
    text = (text or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    m = _YT_ID.search(text)
    return m.group(1) if m else None


# --- cached data ----------------------------------------------------------


@st.cache_resource
def _ensure_db() -> bool:
    init_db()
    return True


@st.cache_data(show_spinner="Computing benchmarks...")
def get_benchmarks() -> tuple[dict, dict]:
    return compute_benchmark(), compute_timeline_benchmark()


@st.cache_data(show_spinner="Computing per-second benchmark...")
def get_ps_benchmark() -> dict:
    return compute_per_second_benchmark(label_scheme=LABEL_SCHEME, niche="fitness")


@st.cache_data(show_spinner="Loading corpus...")
def load_corpus() -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Video.title, Channel.title, VideoLabel.tercile)
            .join(Channel, Channel.id == Video.channel_id)
            # Inner join: only videos with extracted features are analyzable.
            # The metadata-only niches (velocity-collection) are excluded —
            # the analyzer/benchmark exist for fitness only right now.
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .outerjoin(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme == LABEL_SCHEME),
            )
            .order_by(Video.published_at.desc())
        ).all()
    return [
        {"id": vid, "title": title, "channel": chan, "tercile": tercile}
        for vid, title, chan, tercile in rows
    ]


# --- rendering ------------------------------------------------------------


def tercile_badge(tercile: int | None) -> None:
    if tercile is None:
        st.caption("No performance label yet (not in a labeled cohort).")
        return
    name, color = TERCILE[tercile]
    st.markdown(
        f"<span style='background:{color};color:white;padding:3px 10px;"
        f"border-radius:4px;font-size:0.85em;font-weight:600'>{name}</span>",
        unsafe_allow_html=True,
    )


_STATUS_PLAIN = {
    "above": "higher than winners",
    "below": "lower than winners",
    "aligned": "in line with winners",
}


def render_aggregate_table(b) -> None:
    """Full feature comparison table from an already-computed breakdown."""
    if not b.findings:
        st.info("No comparable features for this archetype.")
        return
    hdr = st.columns([3, 1.5, 1.5, 2.2])
    for col, txt in zip(hdr, ("Feature", "This video", "Winners", "Status")):
        col.markdown(f"**{txt}**")
    for f in b.findings:
        c = st.columns([3, 1.5, 1.5, 2.2])
        proxy = "  *(weak signal)*" if f.causal == "likely-proxy" else ""
        c[0].markdown(f"{f.label}{proxy}")
        yours = f"{f.your_value:.1f}{f.unit}" if f.your_value is not None else "n/a"
        c[1].markdown(yours)
        c[2].markdown(f"~{f.benchmark_value:.1f}{f.unit}")
        status = _STATUS_PLAIN.get(f.direction, f.direction)
        if f.direction == "aligned":
            c[3].markdown(f":green[{status}]")
        else:
            c[3].markdown(f":orange[{status}]")


def format_timestamp(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _deviation_color(dev: float | None) -> str:
    """Map a 0-1 deviation to a green->amber->red hex colour. None -> grey."""
    if dev is None:
        return "#d5d8dc"
    d = max(0.0, min(1.0, dev / 0.8))  # saturate at 0.8 so reds are reachable
    if d < 0.5:  # green (#27ae60) -> amber (#f1c40f)
        t = d / 0.5
        r, g, b = 0x27 + t * 0xCA, 0xAE + t * 0x16, 0x60 - t * 0x51
    else:  # amber (#f1c40f) -> red (#c0392b)
        t = (d - 0.5) / 0.5
        r, g, b = 0xF1 - t * 0x31, 0xC4 - t * 0x8B, 0x0F + t * 0x1C
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _cluster_flagged(dev: list[dict], max_clusters: int = 3) -> list[dict]:
    """Group consecutive flagged seconds into ranges; return the worst few.

    Turns a wall of identical per-second flags into a handful of readable
    spans. Seconds within 2s of each other join the same cluster; each cluster
    is summarised by its peak second's deviation and reason.
    """
    flagged = [d for d in dev if d.get("reason")]
    if not flagged:
        return []
    clusters: list[list[dict]] = [[flagged[0]]]
    for d in flagged[1:]:
        if d["second"] - clusters[-1][-1]["second"] <= 2:
            clusters[-1].append(d)
        else:
            clusters.append([d])
    summarised = []
    for c in clusters:
        peak = max(c, key=lambda d: d["deviation"] or 0.0)
        summarised.append(
            {
                "start": c[0]["second"],
                "end": c[-1]["second"],
                "peak_dev": peak["deviation"] or 0.0,
                "reason": peak["reason"],
            }
        )
    summarised.sort(key=lambda x: -x["peak_dev"])
    return summarised[:max_clusters]


def render_timeline(video_id: str, ps_benchmark: dict) -> None:
    try:
        dev = per_second_deviation(video_id, benchmark=ps_benchmark)
    except ValueError as e:
        st.warning(f"Timeline unavailable: {e}")
        return
    if not dev or all(d["deviation"] is None for d in dev):
        st.info(
            "No per-second timeline for this video yet "
            "(it may not be timelined, or it is music-only with no comparable cohort)."
        )
        return

    st.caption(
        "Where this video diverges from winning Shorts of its archetype, second "
        "by second — greener tracks winners, redder diverges. This is a "
        "**prediction from niche patterns, not measured audience retention.**"
    )

    cells = []
    for d in dev:
        color = _deviation_color(d["deviation"])
        ts = format_timestamp(d["second"])
        devtxt = "n/a" if d["deviation"] is None else f"{d['deviation']:.2f}"
        tip = f"{ts}  ·  deviation {devtxt}"
        if d["reason"]:
            tip += f"  ·  {d['reason']}"
        cells.append(
            f"<div title=\"{tip}\" style=\"flex:1;height:34px;background:{color};"
            f"border-right:1px solid #fff\"></div>"
        )
    st.markdown(
        f"<div style='display:flex;width:100%;border-radius:5px;overflow:hidden;"
        f"margin:4px 0'>{''.join(cells)}</div>",
        unsafe_allow_html=True,
    )
    end = format_timestamp(dev[-1]["second"])
    mid = format_timestamp(dev[-1]["second"] // 2)
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;color:#7f8c8d;"
        f"font-size:0.8em'><span>0:00</span><span>{mid}</span><span>{end}</span></div>",
        unsafe_allow_html=True,
    )

    clusters = _cluster_flagged(dev)
    if clusters:
        st.markdown("**Weak-spot ranges** (top few — not every flagged second):")
        for cl in clusters:
            if cl["start"] == cl["end"]:
                span = format_timestamp(cl["start"])
            else:
                span = f"{format_timestamp(cl['start'])}–{format_timestamp(cl['end'])}"
            st.markdown(f"- :orange[**{span}**] — {cl['reason']}")
    else:
        st.markdown(
            ":green[No stretch crosses the weak-spot threshold — framing and "
            "pacing track winning Shorts throughout.]"
        )


def render_frame(video_id: str, frame_benchmark: dict) -> None:
    st.markdown("#### Frame-level breakdown (hook & pacing)")
    try:
        fb = analyze_timeline(video_id, benchmark=frame_benchmark)
    except ValueError as e:
        st.warning(f"Frame breakdown unavailable: {e}")
        return
    if not fb.findings:
        st.info("No frame-level findings.")
        return
    for finding in fb.findings:
        aligned = "aligned" in finding.lower() or "in line" in finding.lower()
        icon = ":green[✓]" if aligned else ":orange[!]"
        st.markdown(f"{icon} {finding}")


def render_analysis(video_id: str) -> None:
    benchmark, frame_benchmark = get_benchmarks()
    try:
        b = analyze_video(video_id, benchmark=benchmark)
    except ValueError as e:
        st.warning(f"Analysis unavailable: {e}")
        return

    arch_plain = ARCHETYPE_PLAIN.get(b.archetype, b.archetype)
    left, right = st.columns([2, 1])
    with left:
        st.subheader(b.title)
        st.caption(
            f"{b.channel}  ·  {b.duration_seconds}s  ·  {arch_plain}  "
            f"(compared against {b.archetype_n} winning {arch_plain}s)"
        )
        tercile_badge(b.tercile)
    with right:
        st.video(f"https://www.youtube.com/watch?v={video_id}")

    # --- The read: plain-English synthesis, leads the page ---
    summary = build_summary(b, frame_benchmark)
    st.markdown("### The read")
    st.write(summary.read)

    if summary.worth_trying:
        st.markdown("**Worth trying** — patterns winners share, not guarantees:")
        for s in summary.worth_trying:
            st.markdown(f"- {s.text}")
    if summary.strengths:
        st.markdown("**Already working**")
        for s in summary.strengths:
            st.markdown(f"- {s}")

    # --- Supporting detail, collapsed by default ---
    st.markdown("---")
    st.caption("Supporting detail")
    with st.expander("Timeline — predicted weak spots, second by second"):
        render_timeline(video_id, get_ps_benchmark())
    with st.expander("Full feature comparison"):
        render_aggregate_table(b)
    with st.expander("Hook & pacing detail"):
        render_frame(video_id, frame_benchmark)


# --- app ------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Creative Director", page_icon="🎬", layout="wide")
    _ensure_db()

    st.title("Creative Director — fitness Shorts analyzer")
    st.caption(
        "Compares a Short against high-performing videos of the same content "
        "archetype. Findings are **correlational** — patterns winners share, "
        "not proven causes — and pre-date velocity-curve labels. Treat as a "
        "hypothesis generator, not validated advice."
    )

    browse_tab, url_tab = st.tabs(["Browse corpus", "Analyze a URL"])

    with browse_tab:
        corpus = load_corpus()
        st.caption(
            f"{len(corpus)} analyzable fitness Shorts. "
            "(Other niches are velocity-collection only — no features extracted yet.)"
        )
        terc_filter = st.radio(
            "Filter by performance",
            ["All", "High", "Mid", "Low"],
            horizontal=True,
        )
        terc_map = {"High": 2, "Mid": 1, "Low": 0}
        shown = corpus
        if terc_filter != "All":
            shown = [v for v in corpus if v["tercile"] == terc_map[terc_filter]]

        if not shown:
            st.info("No videos match this filter.")
        else:
            options = {
                f"{v['title'][:70]}  —  {v['channel']}": v["id"] for v in shown
            }
            choice = st.selectbox("Pick a video", list(options.keys()))
            if choice:
                render_analysis(options[choice])

    with url_tab:
        st.write(
            "Paste a YouTube Shorts URL or video ID. The video is downloaded, "
            "featurized, and timelined on the fly — expect roughly 45–90s on CPU."
        )
        raw = st.text_input("YouTube Shorts URL or ID")
        if st.button("Analyze", type="primary"):
            video_id = parse_video_id(raw)
            if not video_id:
                st.error("Could not parse a video ID from that input.")
            else:
                status = st.status("Ingesting video...", expanded=True)
                try:
                    from creative_director.ingestion.single import (
                        ingest_single_video,
                    )

                    ingest_single_video(
                        video_id, progress=lambda m: status.write(m)
                    )
                    status.update(label="Ingest complete", state="complete")
                    load_corpus.clear()
                    render_analysis(video_id)
                except Exception as e:
                    status.update(label="Ingest failed", state="error")
                    st.error(str(e))


if __name__ == "__main__":
    main()
