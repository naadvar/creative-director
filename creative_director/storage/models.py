from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    handle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    niche: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    subscriber_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    video_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    view_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    uploads_playlist_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    videos: Mapped[list["Video"]] = relationship(back_populates="channel")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_short: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Path to the persisted video file (set when stage-1 downloads to Drive).
    # In stage 2 the Colab processor reads this to extract video-derived features.
    video_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    default_language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    category_id: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Set when a logged-in creator uploads this reel — links uploads → User so we
    # can build a per-creator style fingerprint from their OWN uploads (no scraping).
    # NULL for corpus videos.
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # IG-specific metadata captured from the Apify Reel Scraper output. NULL
    # for YouTube videos and for pre-2026-05-21 IG ingests (backfill from
    # Apify dataset within 7-day retention if needed).
    music_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    mentions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tagged_users: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    dimensions_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dimensions_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comments_disabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    coauthor_producers: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    latest_comments: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Content category (creative_director.advice.categories). category_confirmed
    # is 1 when the creator picked/confirmed it via the dropdown (a training
    # label); 0 when it's the auto keyword guess.
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    category_confirmed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    channel: Mapped[Channel] = relationship(back_populates="videos")
    velocity_snapshots: Mapped[list["VelocitySnapshot"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    features: Mapped[Optional["VideoFeatures"]] = relationship(
        back_populates="video", uselist=False, cascade="all, delete-orphan"
    )


class VelocitySnapshot(Base):
    """Time-series of view/like/comment counts captured at multiple intervals.

    The ratio (view_count at 24h / view_count at 7d) and similar derived signals
    are what we'll use to compute virality labels — much better than raw counts.
    """

    __tablename__ = "velocity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    hours_since_publish: Mapped[float] = mapped_column(Float)
    view_count: Mapped[int] = mapped_column(Integer)
    like_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    favorite_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    video: Mapped[Video] = relationship(back_populates="velocity_snapshots")


class VideoFeatures(Base):
    """Extracted features. One row per video."""

    __tablename__ = "video_features"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), primary_key=True)

    # Thumbnail
    thumb_face_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumb_dominant_face_area: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thumb_text_present: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    thumb_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumb_text_char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumb_brightness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thumb_saturation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thumb_contrast: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thumb_dominant_colors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    thumb_clip_embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Title / description
    title_char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title_word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title_emoji_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title_question_mark: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    title_has_number: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    title_all_caps_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    title_embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    description_char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hashtag_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # First-3-seconds video frame features
    first3s_cut_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    first3s_motion_intensity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    first3s_face_present: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    first3s_text_present: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Full-video frame features
    total_cut_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_shot_length: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Audio
    audio_loudness_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    audio_loudness_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    audio_tempo_bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    audio_voice_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transcript_first_3s: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # v2 features --------------------------------------------------------------
    # Engagement prompt detection (regex on title + description + transcript).
    # All bool-shaped values stored as INTEGER 0/1 (sqlite has no native bool).
    engagement_has_save_prompt: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engagement_has_tag_prompt: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engagement_has_follow_prompt: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engagement_has_comment_prompt: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engagement_has_question_hook: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engagement_prompt_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Hook text (first-3s transcript).
    hook_text_embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    hook_starts_with_question: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hook_uses_you: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hook_uses_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hook_has_negation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hook_word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Hook audio fingerprint (first 1-2s of audio waveform).
    hook_audio_peak_loudness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_audio_mean_loudness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_audio_attack_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_audio_is_voice: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Topic subcluster id (offline k-means per niche over thumb+title PCA).
    topic_cluster_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Music metadata (IG only; NULL for YT).
    music_uses_original: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    music_audio_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    music_audio_id_corpus_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # v3: description (caption) sentence embedding -- 384-dim from all-MiniLM-L6-v2.
    description_embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Wave 2: visual frame features extracted from the mp4 (hook_visual.py).
    hook_face_fill: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_face_headroom: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_frontal_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_face_present_frac: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_background_clutter: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_is_action_first: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hook_motion_first: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_emotion_happy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_emotion_intense: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_emotion_surprised: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_emotion_neutral: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_clip_image_embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Full-video VLM perception (features/vlm_perception.py). null = no VLM run
    # (corpus videos pre-backfill, or no key) -> advice falls back to scalar.
    vlm_perception: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Craft X-ray read (advice/craft_xray.py) — the grounded craft critic output.
    # Cached because it's a strong-VLM call; null = not generated yet.
    craft_read: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    video: Mapped[Video] = relationship(back_populates="features")


class VideoLabel(Base):
    """Performance label for a video under a specific normalization scheme.

    One video can have multiple labels (different schemes, different cohorts).
    Recomputed on demand — labels change as new VelocitySnapshot rows arrive.
    """

    __tablename__ = "video_labels"
    __table_args__ = (
        UniqueConstraint("video_id", "label_scheme", name="uq_video_labels_video_scheme"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    label_scheme: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    tercile: Mapped[int] = mapped_column(Integer)  # 0=low, 1=medium, 2=high
    cohort_id: Mapped[str] = mapped_column(String(64))
    cohort_size: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VideoTimeline(Base):
    """Per-second analysis of a video (Phase 2). Many rows per video.

    This is the frame-level representation: each row is one second of the
    video with what's on screen (CLIP zero-shot vibe), motion, a cut flag,
    and an on-beat flag. It's what enables "second 0-3 is the problem"
    advice instead of only video-level aggregates.
    """

    __tablename__ = "video_timeline"
    __table_args__ = (
        UniqueConstraint("video_id", "second", name="uq_timeline_video_second"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    second: Mapped[int] = mapped_column(Integer)

    # CLIP zero-shot: the highest-scoring niche prompt, plus the full score dict.
    primary_vibe: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    clip_scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    motion: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    brightness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    has_face: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_cut: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    on_beat: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    """A creator using the app. Auth is either a passwordless email gate (demo
    lead capture) or Instagram Login — no passwords stored. ``email`` is set for
    email-gate users and is the lead-capture signal; OAuth-only users may have
    none."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True, index=True)

    connections: Mapped[list["ConnectedAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ConnectedAccount(Base):
    """An OAuth-connected creator platform account (Instagram first; the schema
    is platform-agnostic so YouTube/TikTok can be added later).

    Tokens are stored to call the platform API on the creator's behalf. For a
    local-first pilot they live in the local SQLite DB; encrypt-at-rest before
    any real deployment (flagged in the API notes)."""

    __tablename__ = "connected_accounts"
    __table_args__ = (
        UniqueConstraint(
            "platform", "platform_user_id", name="uq_connected_platform_user"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)  # "instagram"
    platform_user_id: Mapped[str] = mapped_column(String(64))  # IG user id
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    account_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # BUSINESS/MEDIA_CREATOR
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scopes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped[User] = relationship(back_populates="connections")


class NoteFeedback(Base):
    """A creator's one-tap dismissal of a craft-read note ('not useful' / 'not in
    my reel'). The visible trust affordance AND the cheapest fabrication/quality
    labeling signal — each row is a frame-grounded labeled example for tuning."""

    __tablename__ = "note_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text)  # the dismissed (or endorsed) note text
    reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # helpful / not_useful / not_in_reel
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Upload(Base):
    """A creator's uploaded reel + its craft read — the DURABLE record. Lives in the
    separate writable userdata.db (bound via db.SessionLocal) so it SURVIVES corpus
    re-deploys, which overwrite the read-only corpus DB. Self-contained: it holds
    everything the read page + the 'My reads' gallery + the Creator DNA need, so an
    upload renders even after its transient corpus videos/video_features rows are
    wiped. The mp4 + thumbnail themselves live on the persistent volume (paths here)
    and/or R2, which also survive."""

    __tablename__ = "uploads"

    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    niche: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    craft_read: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    video_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    # Revision loop — set only when the creator explicitly re-checks a fix. prior_video_id
    # links this upload to the one it revises; revision_verdict is the self-contained
    # "did my fix land?" result (snapshotted at compute time, so it survives the prior
    # upload being deleted / the corpus rows being wiped). See docs/REVISION_LOOP_DESIGN.md.
    prior_video_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    revision_verdict: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Ideation loop — set when the creator tapped "Plan this next" on a generated idea
    # and shot it. Joins the upload (and its eventual read) back to the CreatorIdea row,
    # so "did the planned guardrail hold?" is answerable later, same explicit-link
    # pattern as prior_video_id (never inferred).
    idea_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)


class CreatorIdea(Base):
    """One generated 'Ideas from your DNA' concept — grounded reel ideation built
    from the creator's OWN reads (never trends). Append-only history; userdata store
    so it survives corpus redeploys. cache_key fingerprints the set of grounded reads
    the idea was built from — a new read changes the key, which is what keeps Growth
    always showing an idea that reflects the latest read."""

    __tablename__ = "creator_ideas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # cdi_<hex>
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    niche: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # The craft gap the idea pre-empts (change_type or opportunity_dimension key).
    gap_dimension: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idea: Mapped[dict] = mapped_column(JSON)  # the validated model output
    source_video_ids: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # cited upload ids
    feedback: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # helpful / not_for_me
    feedback_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
