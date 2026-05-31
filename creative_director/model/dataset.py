"""Build a model-ready feature matrix from the database.

Pulls hand-engineered numeric features plus a small, reduced set of
embedding-derived features. Raw 512/384-dim embeddings are NOT fed directly
(that many dims on a few hundred rows would overfit badly) — they are reduced
with PCA, and summarised as similarity-to-winner-centroid.

Feature provenance — IMPORTANT for honest evaluation:
  - Most features are intrinsic to the video (thumbnail, title, audio, timeline)
    and PCA components — none of these touch the label.
  - A few features ARE label-derived: the per-second deviation summary and the
    winner-centroid similarities are computed against *winning* videos, so they
    leak a little label information. They are listed in LABEL_DERIVED_FEATURES.
    The benchmark here is built over the FULL corpus, so on a time-aware split
    the deviation/sim features carry a mild optimistic bias. The leak-free
    version computes the winner benchmark from the training fold only — see
    train.py for where that belongs as a follow-up.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select

from creative_director.features.derived import (
    HOOK_SECONDS,
    audio_dynamic_range,
    body_clip_profile,
    channel_temporal_features,
    cosine as derived_cosine,
    description_text_features,
    hook_clip_profile,
    music_artist_is_known,
    speech_pace_wpm,
    timeline_shape,
    title_text_features,
    transcript_text_features,
)
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel


# Numeric columns read straight off VideoFeatures.
_VIDEOFEATURE_COLUMNS = [
    "thumb_face_count",
    "thumb_dominant_face_area",
    "thumb_text_present",
    "thumb_text_char_count",
    "thumb_brightness",
    "thumb_saturation",
    "thumb_contrast",
    "title_char_count",
    "title_word_count",
    "title_emoji_count",
    "title_question_mark",
    "title_has_number",
    "title_all_caps_ratio",
    "description_char_count",
    "hashtag_count",
    "first3s_cut_count",
    "first3s_motion_intensity",
    "first3s_face_present",
    "first3s_text_present",
    "total_cut_count",
    "avg_shot_length",
    "audio_loudness_mean",
    "audio_loudness_max",
    "audio_tempo_bpm",
    "audio_voice_ratio",
    "transcript_word_count",
    # v2: engagement-prompt detection
    "engagement_has_save_prompt",
    "engagement_has_tag_prompt",
    "engagement_has_follow_prompt",
    "engagement_has_comment_prompt",
    "engagement_has_question_hook",
    "engagement_prompt_count",
    # v2: hook text (first-3s transcript) interpretable flags
    "hook_starts_with_question",
    "hook_uses_you",
    "hook_uses_number",
    "hook_has_negation",
    "hook_word_count",
    # v2: music metadata (IG only; NaN for YT, handled by LightGBM)
    "music_uses_original",
    "music_audio_id_corpus_uses",
    # Wave 2: visual frame features (from mp4; NaN for reels without mp4)
    "hook_face_fill",
    "hook_face_headroom",
    "hook_frontal_ratio",
    "hook_face_present_frac",
    "hook_background_clutter",
    "hook_is_action_first",
    "hook_motion_first",
    "hook_emotion_happy",
    "hook_emotion_intense",
    "hook_emotion_surprised",
    "hook_emotion_neutral",
    # v2: hook-audio fingerprint (first 1-2s of audio waveform).
    # NOTE: these added pure noise on CV (Spearman 0.507 -> 0.486) -- the
    # model overfits the per-row variability of librosa's 2s decode. Backfilled
    # columns retained for forensic value but excluded from the trained set.
    # "hook_audio_peak_loudness",
    # "hook_audio_mean_loudness",
    # "hook_audio_attack_rate",
    # "hook_audio_is_voice",
]

# v3: derived features computed at dataset-build time (no DB storage).
_DERIVED_V3_COLUMNS = [
    # Timeline-shape aggregates
    "tl_hook_motion_std",
    "tl_hook_brightness_var",
    "tl_motion_curve_slope",
    "tl_motion_peak_position",
    "tl_longest_static_stretch",
    "tl_cut_interval_std",
    "tl_cuts_in_first_half_ratio",
    "tl_face_consistency",
    "tl_vibe_transition_count",
    # Hook -> body visual coherence (cosine of hook clip-score vector vs body)
    "tl_hook_body_clip_cosine",
    # Text-derived
    "title_starts_imperative",
    "description_first_line_chars",
    "description_word_count",
    "description_link_count",
    "description_has_promo",
    "transcript_question_count",
    "transcript_uses_you_count",
    "speech_pace_wpm",
    "audio_dynamic_range",
    "music_artist_is_known",
    # Channel temporal
    "creator_days_since_last_post",
    "creator_posting_rate_30d",
    "creator_total_reels_at_publish",
    "creator_is_first_10_reels",
]

# v2: topic-subcluster one-hot. K=8 by convention (see features/topic_cluster.py).
_TOPIC_K = 8
_TOPIC_COLUMNS = [f"topic_cluster_{i}" for i in range(_TOPIC_K)]

# Derived columns used as model features.
# NOTE: log_subscriber_count is computed in build_dataframe but deliberately
# NOT a feature — the views/subs labels contain subscriber count in their
# definition, so feeding it as a feature would leak the label.
_DERIVED_COLUMNS = [
    "duration_seconds",
    "publish_hour",
    "publish_dow",
]

# Phase 2 timeline-derived features (per-second VideoTimeline rows aggregated
# per video). Null for videos with no timeline extracted.
_TIMELINE_COLUMNS = [
    "tl_hook_face_frac",
    "tl_first_cut_second",
    "tl_cuts_per_10s",
    "tl_cut_count",
    "tl_distinct_vibes",
]

# PCA components of the stored CLIP/text embeddings. Unsupervised — no label
# leakage. Counts kept small relative to the row count.
_THUMB_PCA_K = 8
_TITLE_PCA_K = 6
_HOOK_PCA_K = 6
_DESC_PCA_K = 6
_HOOKIMG_PCA_K = 8  # Wave 2: CLIP image embedding of the hook frames
_EMBEDDING_COLUMNS = (
    [f"thumb_clip_pca_{i}" for i in range(_THUMB_PCA_K)]
    + [f"title_emb_pca_{i}" for i in range(_TITLE_PCA_K)]
    + [f"hook_text_pca_{i}" for i in range(_HOOK_PCA_K)]
    + [f"desc_emb_pca_{i}" for i in range(_DESC_PCA_K)]
    + [f"hook_img_pca_{i}" for i in range(_HOOKIMG_PCA_K)]
)

# Summary of the per-second deviation curve — gives LightGBM the shape signal a
# sequence model would otherwise read directly. LABEL-DERIVED (see module note).
_DEVIATION_COLUMNS = [
    "dev_mean",
    "dev_max",
    "dev_worst_rel",
    "dev_hook_mean",
    "dev_body_mean",
    "dev_front_back",
    "dev_flagged_frac",
]

# Cosine similarity of this video's embedding to the winner centroid.
# LABEL-DERIVED (see module note).
_WINNER_SIM_COLUMNS = [
    "thumb_sim_winner",
    "title_sim_winner",
    "hook_text_sim_winner",
    "desc_emb_sim_winner",
    "hook_clip_profile_sim_winner",
    "hook_img_sim_winner",
]

# Features that touch the label and therefore carry optimistic bias on a
# time-aware split unless the winner benchmark is rebuilt per training fold.
LABEL_DERIVED_FEATURES: list[str] = _DEVIATION_COLUMNS + _WINNER_SIM_COLUMNS

FEATURE_NAMES: list[str] = (
    _VIDEOFEATURE_COLUMNS
    + _DERIVED_COLUMNS
    + _TIMELINE_COLUMNS
    + _DERIVED_V3_COLUMNS
    + _EMBEDDING_COLUMNS
    + _TOPIC_COLUMNS
    + _DEVIATION_COLUMNS
    + _WINNER_SIM_COLUMNS
)

# Features safe to use without per-fold benchmark recomputation.
INTRINSIC_FEATURES: list[str] = [
    f for f in FEATURE_NAMES if f not in LABEL_DERIVED_FEATURES
]


def _to_float(v) -> float:
    """Coerce DB values (incl. bool and None) to float; None -> NaN."""
    if v is None:
        return np.nan
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def _coerce_embedding(raw, dim: int) -> Optional[np.ndarray]:
    """JSON embedding column -> float vector of length dim, or None."""
    if not raw:
        return None
    try:
        vec = np.asarray(raw, dtype=float)
    except (TypeError, ValueError):
        return None
    if vec.shape != (dim,):
        return None
    return vec


def _pca_block(vectors: list[Optional[np.ndarray]], dim: int, k: int) -> np.ndarray:
    """PCA-reduce a list of (possibly missing) embedding vectors to k columns.

    Missing rows are imputed with the column mean before fitting, then their
    PCA scores are left at the dataset mean (zeros after centering).
    """
    from sklearn.decomposition import PCA

    n = len(vectors)
    present = [v for v in vectors if v is not None]
    if len(present) < k + 1:
        # Not enough rows to fit k components — emit zeros.
        return np.zeros((n, k), dtype=float)

    mean_vec = np.mean(np.stack(present), axis=0)
    mat = np.stack([v if v is not None else mean_vec for v in vectors])
    scores = PCA(n_components=k, random_state=42).fit_transform(mat)
    # Blank out imputed rows so they don't masquerade as real signal.
    for i, v in enumerate(vectors):
        if v is None:
            scores[i] = 0.0
    return scores


def _winner_similarity(
    vectors: list[Optional[np.ndarray]], terciles: list[int]
) -> np.ndarray:
    """Cosine similarity of each embedding to the mean winner (tercile==2) embedding."""
    n = len(vectors)
    winners = [
        v for v, t in zip(vectors, terciles) if v is not None and t == 2
    ]
    if not winners:
        return np.full(n, np.nan)
    centroid = np.mean(np.stack(winners), axis=0)
    c_norm = np.linalg.norm(centroid)
    out = np.full(n, np.nan)
    if c_norm == 0:
        return out
    for i, v in enumerate(vectors):
        if v is None:
            continue
        v_norm = np.linalg.norm(v)
        if v_norm == 0:
            continue
        out[i] = float(np.dot(v, centroid) / (v_norm * c_norm))
    return out


def build_dataframe(
    label_scheme: str = "per_channel_log_residual_v1",
    niche: "str | list[str] | None" = "fitness",
) -> pd.DataFrame:
    """One row per labeled+featurized video. Columns: FEATURE_NAMES + target + meta."""
    # Lazy import avoids a circular import at module load
    # (timeline_benchmark -> benchmark -> dataset).
    from creative_director.advice.benchmark import classify_archetype
    from creative_director.advice.timeline_benchmark import (
        compute_per_second_benchmark,
        deviation_from_rows,
        summarize_deviation,
        summarize_timeline,
    )
    from creative_director.storage.models import VideoTimeline

    # Per-second winner benchmark for the deviation features. Built once over
    # the full corpus (see module note on the resulting mild optimistic bias).
    _bench_niche = niche if isinstance(niche, str) else (
        next(iter(niche)) if niche else "fitness"
    )
    ps_benchmark = compute_per_second_benchmark(
        label_scheme=label_scheme, niche=_bench_niche
    )

    rows: list[dict] = []
    thumb_vecs: list[Optional[np.ndarray]] = []
    title_vecs: list[Optional[np.ndarray]] = []
    hook_vecs: list[Optional[np.ndarray]] = []
    desc_vecs: list[Optional[np.ndarray]] = []
    hookimg_vecs: list[Optional[np.ndarray]] = []  # Wave 2: hook CLIP image emb
    # Hook & body CLIP-profile vectors: dict[prompt]->mean score for each video.
    # We harmonise to a single sorted-key list after the loop so winner-sim works.
    hook_clip_dicts: list[Optional[dict]] = []
    body_clip_dicts: list[Optional[dict]] = []

    with session_scope() as s:
        q = (
            select(Video, VideoFeatures, Channel, VideoLabel)
            .join(VideoFeatures, Video.id == VideoFeatures.video_id)
            .join(Channel, Video.channel_id == Channel.id)
            .join(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme == label_scheme),
            )
        )
        if niche:
            if isinstance(niche, str):
                q = q.where(Channel.niche == niche)
            else:
                q = q.where(Channel.niche.in_(list(niche)))
        results = s.execute(q).all()

        # Batch-load per-second timeline rows for all videos in scope, group by video.
        video_ids = [v.id for v, _f, _c, _l in results]
        timelines: dict[str, list] = {}
        if video_ids:
            for tl in (
                s.execute(
                    select(VideoTimeline).where(VideoTimeline.video_id.in_(video_ids))
                )
                .scalars()
                .all()
            ):
                timelines.setdefault(tl.video_id, []).append(tl)

        # Batch-load every publish_at for each channel in scope so the channel
        # temporal features don't trigger N+1 queries.
        channel_ids = {c.id for _v, _f, c, _l in results}
        channel_pubs: dict[str, list] = {}
        if channel_ids:
            for cid, pa in s.execute(
                select(Video.channel_id, Video.published_at).where(
                    Video.channel_id.in_(channel_ids)
                )
            ).all():
                channel_pubs.setdefault(cid, []).append(pa)

        # Pre-fetch music_info on the source Video row (already loaded via the
        # outer query). For YT videos this stays None.

        for video, feat, channel, label in results:
            row = {c: _to_float(getattr(feat, c)) for c in _VIDEOFEATURE_COLUMNS}
            row["duration_seconds"] = _to_float(video.duration_seconds)
            row["publish_hour"] = float(video.published_at.hour)
            row["publish_dow"] = float(video.published_at.weekday())
            row["log_subscriber_count"] = math.log(
                max(1, channel.subscriber_count or 1)
            )

            tl_rows = sorted(
                timelines.get(video.id, []), key=lambda r: r.second
            )

            # Phase 2 timeline features (NaN if no timeline extracted for this video).
            summ = summarize_timeline(tl_rows)
            if summ:
                row["tl_hook_face_frac"] = _to_float(summ["hook_face_frac"])
                row["tl_first_cut_second"] = _to_float(summ["first_cut_second"])
                row["tl_cuts_per_10s"] = _to_float(summ["cuts_per_10s"])
                row["tl_cut_count"] = _to_float(summ["cut_count"])
                row["tl_distinct_vibes"] = _to_float(summ["distinct_vibes"])
            else:
                for c in _TIMELINE_COLUMNS:
                    row[c] = np.nan

            # v3 timeline-shape features (motion variance, energy slope, etc.).
            shape = timeline_shape(tl_rows)
            for k, v in shape.items():
                row[k] = _to_float(v)

            # Hook & body CLIP zero-shot profiles (mean per-prompt score).
            hk_vec, hk_keys = hook_clip_profile(tl_rows)
            bd_vec, bd_keys = body_clip_profile(tl_rows)
            hook_clip_dicts.append(
                dict(zip(hk_keys, hk_vec.tolist())) if hk_vec is not None else None
            )
            body_clip_dicts.append(
                dict(zip(bd_keys, bd_vec.tolist())) if bd_vec is not None else None
            )
            row["tl_hook_body_clip_cosine"] = derived_cosine(hk_vec, bd_vec)

            # Text derived (title + description + transcript).
            for k, v in title_text_features(video.title).items():
                row[k] = float(v)
            for k, v in description_text_features(video.description).items():
                row[k] = float(v)
            for k, v in transcript_text_features(feat.transcript).items():
                row[k] = float(v)
            row["speech_pace_wpm"] = speech_pace_wpm(
                feat.transcript_word_count,
                feat.audio_voice_ratio,
                video.duration_seconds,
            )

            # Audio dynamic range from existing extracted features.
            row["audio_dynamic_range"] = audio_dynamic_range(
                feat.audio_loudness_max, feat.audio_loudness_mean
            )

            # Music metadata (artist-is-known beyond raw music_uses_original).
            row["music_artist_is_known"] = music_artist_is_known(video.music_info)

            # Channel temporal cadence features (gap since last post, etc.).
            temporal = channel_temporal_features(
                channel_pubs.get(channel.id, []), video.published_at
            )
            for k, v in temporal.items():
                row[k] = float(v) if v is not None else np.nan

            # Per-second deviation summary (NaN if no timeline).
            dev_summ = None
            if tl_rows:
                arch = classify_archetype(feat.transcript_word_count)
                dev = deviation_from_rows(arch, tl_rows, ps_benchmark)
                dev_summ = summarize_deviation(dev)
            if dev_summ:
                for c in _DEVIATION_COLUMNS:
                    row[c] = _to_float(dev_summ[c])
            else:
                for c in _DEVIATION_COLUMNS:
                    row[c] = np.nan

            thumb_vecs.append(_coerce_embedding(feat.thumb_clip_embedding, 512))
            title_vecs.append(_coerce_embedding(feat.title_embedding, 384))
            hook_vecs.append(_coerce_embedding(feat.hook_text_embedding, 384))
            desc_vecs.append(_coerce_embedding(feat.description_embedding, 384))
            hookimg_vecs.append(_coerce_embedding(feat.hook_clip_image_embedding, 512))

            # Topic cluster one-hot encoding.
            cid = feat.topic_cluster_id
            for i in range(_TOPIC_K):
                row[f"topic_cluster_{i}"] = 1.0 if cid == i else 0.0

            row["tercile"] = int(label.tercile)
            row["score"] = float(label.score)
            row["published_at"] = video.published_at
            row["video_id"] = video.id
            row["channel"] = channel.title
            row["niche"] = channel.niche
            rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # --- Embedding-derived columns (added after the loop: PCA and the winner
    # centroid both need the whole set) ---
    thumb_pca = _pca_block(thumb_vecs, 512, _THUMB_PCA_K)
    title_pca = _pca_block(title_vecs, 384, _TITLE_PCA_K)
    hook_pca = _pca_block(hook_vecs, 384, _HOOK_PCA_K)
    desc_pca = _pca_block(desc_vecs, 384, _DESC_PCA_K)
    hookimg_pca = _pca_block(hookimg_vecs, 512, _HOOKIMG_PCA_K)
    for i in range(_THUMB_PCA_K):
        df[f"thumb_clip_pca_{i}"] = thumb_pca[:, i]
    for i in range(_TITLE_PCA_K):
        df[f"title_emb_pca_{i}"] = title_pca[:, i]
    for i in range(_HOOK_PCA_K):
        df[f"hook_text_pca_{i}"] = hook_pca[:, i]
    for i in range(_DESC_PCA_K):
        df[f"desc_emb_pca_{i}"] = desc_pca[:, i]
    for i in range(_HOOKIMG_PCA_K):
        df[f"hook_img_pca_{i}"] = hookimg_pca[:, i]

    terciles = df["tercile"].tolist()
    df["thumb_sim_winner"] = _winner_similarity(thumb_vecs, terciles)
    df["title_sim_winner"] = _winner_similarity(title_vecs, terciles)
    df["hook_text_sim_winner"] = _winner_similarity(hook_vecs, terciles)
    df["desc_emb_sim_winner"] = _winner_similarity(desc_vecs, terciles)
    df["hook_img_sim_winner"] = _winner_similarity(hookimg_vecs, terciles)

    # Hook-CLIP-profile winner-sim: harmonise hook profile dicts onto a single
    # canonical key order (union across all videos), then run winner-sim. NaN
    # for videos with no hook clip scores.
    canonical_keys = sorted(
        {k for d in hook_clip_dicts if d for k in d}
    )
    if canonical_keys:
        canon_hook_vecs: list[Optional[np.ndarray]] = []
        for d in hook_clip_dicts:
            if d:
                canon_hook_vecs.append(
                    np.array([d.get(k, 0.0) for k in canonical_keys], dtype=float)
                )
            else:
                canon_hook_vecs.append(None)
        df["hook_clip_profile_sim_winner"] = _winner_similarity(
            canon_hook_vecs, terciles
        )
    else:
        df["hook_clip_profile_sim_winner"] = np.nan

    return df
