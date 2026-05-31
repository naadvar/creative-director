#!/usr/bin/env bash
# Wait for the extraction process (PID = $1) to finish, then back the DB up to
# R2 (r2:$R2_BUCKET/db/creative_director.db). Decouples the multi-hour run from
# my session: when the DB lands in R2, extraction is done and the result is
# safe even if the pod is terminated. Run detached:
#   nohup bash scripts/dbwatch.sh <extraction_pid> > /workspace/dbwatch.log 2>&1 &
set -uo pipefail
cd /workspace/creative-director
PID="${1:?usage: dbwatch.sh <extraction_pid>}"

echo "watching extraction pid $PID ..."
while kill -0 "$PID" 2>/dev/null; do sleep 60; done
echo "extraction pid $PID exited; uploading DB to R2"

set -a; source .env; set +a
rclone copyto data/creative_director.db "r2:${R2_BUCKET}/db/creative_director.db" \
  && echo "DB_UPLOADED_TO_R2 $(date -u)" >> /workspace/extract.log \
  && echo "DB backup complete: r2:${R2_BUCKET}/db/creative_director.db"
