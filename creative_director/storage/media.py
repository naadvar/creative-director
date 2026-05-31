"""Cloudflare R2 (S3-compatible) media store for the video corpus.

The corpus mp4s + thumbnails are the non-reproducible raw asset (IG CDN URLs
expire), so they live in R2: persistent, zero-egress, and the same bucket the
deployed app and the GPU pod both read from.

Everything here is a no-op unless ``settings.r2_enabled`` (all four core R2
fields set), so local-disk dev is unchanged until you add credentials.

Bucket layout:
    videos/{video_id}.mp4
    thumbnails/{video_id}.jpg

boto3 is imported lazily so it's only required when R2 is actually used.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from creative_director.config import settings

_VIDEO_PREFIX = "videos"
_THUMB_PREFIX = "thumbnails"


def video_key(video_id: str) -> str:
    return f"{_VIDEO_PREFIX}/{video_id}.mp4"


def thumb_key(video_id: str) -> str:
    return f"{_THUMB_PREFIX}/{video_id}.jpg"


@lru_cache(maxsize=1)
def _client():
    """Cached boto3 S3 client pointed at the R2 endpoint."""
    import boto3  # lazy: only needed when R2 is configured
    from botocore.config import Config

    endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        # R2 ignores region but boto3 requires one; "auto" is conventional.
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def upload(local_path: Path, key: str, content_type: str) -> None:
    """Upload a local file to the R2 bucket under ``key``."""
    _client().upload_file(
        str(local_path),
        settings.r2_bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )


def exists(key: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        _client().head_object(Bucket=settings.r2_bucket, Key=key)
        return True
    except ClientError:
        return False


def url_for(key: str, expires: int = 3600) -> str:
    """Public URL for ``key`` — a static public/custom-domain URL when one is
    configured (true zero-egress), else a short-lived presigned GET URL."""
    if settings.r2_public_base_url:
        return f"{settings.r2_public_base_url.rstrip('/')}/{key}"
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket, "Key": key},
        ExpiresIn=expires,
    )


# --- convenience wrappers used by the pipeline + API -----------------------


def mirror_video(local_path: Path, video_id: str) -> None:
    upload(local_path, video_key(video_id), "video/mp4")


def mirror_thumbnail(local_path: Path, video_id: str) -> None:
    upload(local_path, thumb_key(video_id), "image/jpeg")


def video_url(video_id: str) -> Optional[str]:
    return url_for(video_key(video_id)) if settings.r2_enabled else None


def thumbnail_url(video_id: str) -> Optional[str]:
    return url_for(thumb_key(video_id)) if settings.r2_enabled else None
