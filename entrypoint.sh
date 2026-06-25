#!/usr/bin/env bash
# Serve-only container entrypoint: keep the local corpus DB in sync with R2, then
# start the API. The DB lives on a persistent volume (/app/data), so a plain
# "fetch if absent" would pin the live site to whatever was first downloaded and
# never pick up a new corpus. Instead we compare the R2 object's ETag to a stored
# marker and re-fetch only when it changed — so every redeploy after a DB upload
# auto-syncs (~30-60s), while an unchanged DB is skipped instantly.
set -euo pipefail
cd /app
mkdir -p data

python - <<'PY'
import os, boto3
key = "db/creative_director.db"
dbp = "data/creative_director.db"
marker = "data/.db_etag"
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
)
bucket = os.environ["R2_BUCKET"]
try:
    remote = s3.head_object(Bucket=bucket, Key=key)["ETag"].strip('"')
except Exception as e:  # network/credential issue — fall back to "fetch if absent"
    print(f"[entrypoint] R2 head_object failed ({type(e).__name__}); "
          f"{'using existing DB' if os.path.exists(dbp) else 'attempting fetch anyway'}.")
    if os.path.exists(dbp):
        raise SystemExit(0)
    remote = None
have = None
if os.path.exists(marker) and os.path.exists(dbp):
    have = open(marker).read().strip()
if remote is not None and have == remote:
    print(f"[entrypoint] DB up-to-date (etag {remote[:16]}…) — skipping fetch.")
else:
    print(f"[entrypoint] DB stale/absent (have={str(have)[:16]}, remote={str(remote)[:16]}) — fetching…")
    s3.download_file(bucket, key, dbp)
    if remote:
        open(marker, "w").write(remote)
    print("[entrypoint] DB fetched + etag marker updated.")
PY

exec python -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
