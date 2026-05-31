#!/usr/bin/env bash
# Pod-to-pod mp4 transfer: stream the videos/ dir from THIS (old) pod to the
# new GPU pod via tar over ssh. Run detached on the old pod:
#   nohup bash scripts/pod_xfer_videos.sh > /workspace/xfer.log 2>&1 &
set -uo pipefail

KEY=/root/.ssh/id_xfer
NEWPOD=root@103.196.86.125
PORT=12429
SRC=/workspace/creative-director/data

chmod 600 "$KEY" 2>/dev/null || true
cd "$SRC"
echo "=== XFER START $(date) -- $(du -sh videos) ==="
# Stream tar; -C on the receiving side lands it at the same relative path.
tar cf - videos | ssh -i "$KEY" -p "$PORT" -o StrictHostKeyChecking=no "$NEWPOD" \
  "mkdir -p /workspace/creative-director/data && cd /workspace/creative-director/data && tar xf -"
RC=$?
echo "=== XFER DONE rc=$RC $(date) ==="
