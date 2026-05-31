#!/usr/bin/env bash
# Serve-only container entrypoint: fetch the corpus DB from R2 (once, if absent),
# then start the API. On a host with a persistent disk the DB is fetched on first
# boot only; on an ephemeral host it re-fetches each cold start (~30-60s).
set -euo pipefail
cd /app
mkdir -p data

DB="data/creative_director.db"
if [ ! -f "$DB" ]; then
  echo "[entrypoint] corpus DB absent — fetching from R2 (db/creative_director.db)…"
  python - <<'PY'
import os, boto3
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
)
s3.download_file(os.environ["R2_BUCKET"], "db/creative_director.db", "data/creative_director.db")
print("[entrypoint] DB fetched.")
PY
else
  echo "[entrypoint] corpus DB present — skipping fetch."
fi

exec python -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
