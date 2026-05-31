#!/usr/bin/env bash
# One-shot setup on a fresh RunPod box (run AFTER scp'ing code + .env + DB).
# Installs deps with the known-good pins, installs+configures rclone for R2,
# and verifies GPU+R2 before you launch the extraction.
#
#   cd /workspace/creative-director && bash scripts/pod_setup.sh
#   then: bash scripts/runpod_niches.sh
set -euo pipefail
cd /workspace/creative-director

echo "== [0/5] system deps + pod env fixups =="
# ffmpeg: librosa/audioread needs it to decode reel audio (music/tempo features).
# tesseract: thumbnail OCR features. The base image ships neither.
apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq ffmpeg tesseract-ocr >/dev/null 2>&1 \
  || echo "WARN: apt install ffmpeg/tesseract failed - audio/OCR features will be empty"
# The .env came from the laptop: FORCE_CPU=true and a duty-cycle cooldown are
# right for a thermally-limited laptop but DISASTROUS on a rented GPU (ignores
# the GPU; ~11h of idle pauses). Force GPU + no cooldown for the pod.
sed -i 's/^FORCE_CPU=.*/FORCE_CPU=false/' .env 2>/dev/null || true
sed -i 's/^COOLDOWN_EVERY_N_VIDEOS=.*/COOLDOWN_EVERY_N_VIDEOS=0/' .env 2>/dev/null || true
grep -q '^CPU_THERMAL_PAUSE_THRESHOLD=' .env || echo 'CPU_THERMAL_PAUSE_THRESHOLD=0' >> .env

echo "== [1/5] python deps =="
# The base image ships a distutils-installed blinker 1.4 that pip can't
# uninstall when a dep (streamlit/flask) wants a newer one. Install a
# pip-managed copy first so the requirements resolve cleanly.
pip install -q --ignore-installed blinker
pip install -q -r requirements.txt
# numpy 2.x breaks torch's import; sentence-transformers/transformers/hub combo
# below is the version set that imported cleanly on the earlier pods.
pip install -q "numpy<2"
pip install -q "sentence-transformers==2.7.0" "transformers==4.40.2" "huggingface_hub<0.25" || \
  echo "WARN: ST/transformers pin failed - description-embedding feature may degrade (non-fatal)"

echo "== [2/5] rclone =="
command -v rclone >/dev/null || (curl -s https://rclone.org/install.sh | bash)

echo "== [3/5] rclone [r2] remote from .env =="
set -a; source .env; set +a
mkdir -p ~/.config/rclone
cat > ~/.config/rclone/rclone.conf <<EOF
[r2]
type = s3
provider = Cloudflare
access_key_id = ${R2_ACCESS_KEY_ID}
secret_access_key = ${R2_SECRET_ACCESS_KEY}
endpoint = https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com
acl = private
EOF

echo "== [4/5] verify R2 reachable =="
rclone lsd "r2:${R2_BUCKET}" >/dev/null && echo "  rclone R2 OK ($(rclone size r2:${R2_BUCKET}/videos --json 2>/dev/null | python -c 'import sys,json;d=json.load(sys.stdin);print(d["count"],"videos")' 2>/dev/null || echo '?'))"

echo "== [5/5] verify torch CUDA =="
python -c "import torch; assert torch.cuda.is_available(); print('  CUDA OK:', torch.cuda.get_device_name(0))"

echo ""
echo "Setup complete. Next: bash scripts/runpod_niches.sh"
