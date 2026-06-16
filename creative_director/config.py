from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    youtube_api_key: str = ""

    database_url: str = "sqlite:///./data/creative_director.db"

    thumbnail_dir: Path = Path("./data/thumbnails")
    temp_video_dir: Path = Path("./data/tmp")

    enable_video_download: bool = True
    enable_audio_transcript: bool = True
    enable_clip_embeddings: bool = True
    enable_face_detection: bool = True
    enable_ocr: bool = True

    whisper_model: str = "base"
    clip_model: str = "ViT-B-32"
    clip_pretrained: str = "laion2b_s34b_b79k"

    tesseract_path: Optional[str] = None
    max_video_height: int = 720

    # Residential proxy URL for yt-dlp (e.g. Decodo: http://user:pass@gate.decodo.com:7000).
    # Only used for video downloads; the YouTube Data API doesn't need a proxy.
    ytdlp_proxy: Optional[str] = None

    # Hybrid pipeline: if set, the local stage-1 download keeps video files at this
    # path (instead of deleting them). Stage-2 (Colab) reads from these paths.
    # Example: ./data/videos
    video_archive_dir: Optional[Path] = None

    # Hybrid stage flags.
    # Set both to False to skip video downloads entirely (thumbnail-only mode).
    # Stage 1 (local): download_videos=True, extract_video_features=False
    # Stage 2 (Colab): download_videos=False, extract_video_features=True
    extract_video_features: bool = True

    # CPU thermal guard threshold (degrees Celsius). When the CPU package temp
    # reaches this, the pipeline pauses between videos until it cools below
    # (threshold - 5). Set to 0 to disable.
    cpu_thermal_pause_threshold: int = 95

    # Force all ML models (CLIP, Whisper) onto CPU even if a CUDA device is
    # visible. Needed when the local GPU is thermally throttled and slower
    # than the CPU.
    force_cpu: bool = False

    # Cap the number of CPU threads ML inference may use (0 = unlimited).
    # Limiting this lowers peak CPU power draw and temperature — needed on
    # this laptop, which pins at TjMAX (100 C) under full all-core load.
    cpu_threads: int = 0

    # Instagram ingestion (instaloader) — personal-V1 path only. Use a BURNER
    # account, never your main: scraping risks the account. Blank = anonymous
    # (Instagram walls much of its content to anonymous clients, so a burner
    # login is usually needed in practice).
    instagram_user: Optional[str] = None
    instagram_password: Optional[str] = None

    # Duty-cycle thermal cooldown: after every N processed videos, pause for
    # `cooldown_seconds` to let the CPU settle. Set N to 0 to disable.
    cooldown_every_n_videos: int = 0
    cooldown_seconds: int = 60

    # Anthropic API — used by the advice narration layer (advice/narrate.py) and
    # the full-video VLM perception layer (features/vlm_perception.py).
    anthropic_api_key: Optional[str] = None
    narrator_model: str = "claude-opus-4-7"
    # Run the VLM perception pass in the upload job (one Claude call / upload,
    # ~$0.05-0.10). Off by default so corpus/no-key paths fall back to scalar.
    enable_vlm_perception: bool = False

    # Apify — public-data Instagram ingestion path (training-corpus bootstrap
    # only; not the permanent product foundation per the project kill-criterion).
    # Get a Personal API token at Apify Console > Settings > Integrations.
    apify_api_token: Optional[str] = None
    apify_instagram_reel_actor: str = "apify/instagram-reel-scraper"
    apify_instagram_profile_actor: str = "apify/instagram-profile-scraper"

    # Cloudflare R2 — the persistent video corpus + deploy storage backend
    # (S3-compatible, zero egress). When all four core fields are set, the
    # ingest pipeline mirrors mp4s/thumbs to R2 and the API serves them from
    # there; unset = pure local-disk behavior (unchanged).
    #   r2_account_id        Cloudflare account id (R2 endpoint host)
    #   r2_access_key_id      R2 API token access key
    #   r2_secret_access_key  R2 API token secret
    #   r2_bucket             bucket name (e.g. "creative-director-corpus")
    #   r2_public_base_url    optional public/custom-domain URL for zero-egress
    #                         serving (e.g. https://pub-xxxx.r2.dev). If unset,
    #                         the API hands out short-lived presigned URLs.
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket: Optional[str] = None
    r2_public_base_url: Optional[str] = None
    # After mirroring a freshly-ingested mp4 to R2, delete the local copy so the
    # ingest box (your laptop) doesn't accumulate the corpus. Extraction reads
    # the videos on the GPU pod via rclone, not here.
    r2_prune_local: bool = True

    log_level: str = "INFO"

    @property
    def r2_enabled(self) -> bool:
        return bool(
            self.r2_account_id
            and self.r2_access_key_id
            and self.r2_secret_access_key
            and self.r2_bucket
        )


settings = Settings()
settings.thumbnail_dir.mkdir(parents=True, exist_ok=True)
settings.temp_video_dir.mkdir(parents=True, exist_ok=True)
