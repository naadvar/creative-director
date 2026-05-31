"""Verify Cloudflare R2 credentials end-to-end (upload -> list -> read -> delete).

Run this AFTER putting the R2 settings in .env:

    R2_ACCOUNT_ID=...              # Cloudflare dashboard -> R2 -> "Account ID"
    R2_ACCESS_KEY_ID=...           # R2 -> Manage API Tokens -> Create (S3 creds)
    R2_SECRET_ACCESS_KEY=...
    R2_BUCKET=creative-director-corpus
    R2_PUBLIC_BASE_URL=            # optional: bucket Settings -> Public r2.dev URL
                                   #   or a custom domain, for zero-egress serving

    python -m scripts.verify_r2

One-time bucket setup in the Cloudflare dashboard:
  1. R2 -> Create bucket -> name it (match R2_BUCKET).
  2. Manage R2 API Tokens -> Create API token (Object Read & Write) -> copy the
     Access Key ID + Secret (these are the S3 creds above).
  3. (optional) Bucket -> Settings -> enable the public r2.dev URL, paste it as
     R2_PUBLIC_BASE_URL for free zero-egress video serving.

rclone (for the GPU pod to pull the corpus) — add to ~/.config/rclone/rclone.conf:
    [r2]
    type = s3
    provider = Cloudflare
    access_key_id = <R2_ACCESS_KEY_ID>
    secret_access_key = <R2_SECRET_ACCESS_KEY>
    endpoint = https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com
    acl = private
  then:  rclone copy r2:<bucket>/videos data/videos --transfers 16
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from creative_director.config import settings
from creative_director.storage import media


def main() -> None:
    if not settings.r2_enabled:
        print(
            "R2 not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY, R2_BUCKET in .env first."
        )
        sys.exit(1)

    print(f"bucket   = {settings.r2_bucket}")
    print(f"endpoint = https://{settings.r2_account_id}.r2.cloudflarestorage.com")
    print(f"public   = {settings.r2_public_base_url or '(presigned URLs)'}")

    key = "videos/__r2_healthcheck__.mp4"
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"creative-director r2 healthcheck")
        tmp = Path(f.name)

    try:
        print("\n[1/4] upload ...", end=" ")
        media.upload(tmp, key, "video/mp4")
        print("ok")

        print("[2/4] exists ...", end=" ")
        print("ok" if media.exists(key) else "MISSING")

        print("[3/4] url ...", end=" ")
        print(media.url_for(key))

        print("[4/4] delete ...", end=" ")
        media._client().delete_object(Bucket=settings.r2_bucket, Key=key)
        print("ok")

        print("\nR2 is working. ✅")
    finally:
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
