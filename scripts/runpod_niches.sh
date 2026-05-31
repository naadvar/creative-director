#!/usr/bin/env bash
# Extract features/timelines/labels for the new niches on a RunPod GPU box.
#
# THE FLOW (R2 = corpus, RunPod = transient compute):
#   1. LOCAL: ingest each niche (writes mp4s to R2, metadata rows to the DB).
#      DONE 2026-05-29: ig_food (3,433), ig_travel (4,152), ig_fashion (pulling).
#      Use --max-reels 30 (NOT higher) so deep mega-feeds don't blow the timeout.
#   2. Copy the DB up to the pod (it now holds the new metadata rows):
#        scp data/creative_director.db root@<pod>:/workspace/creative-director/data/
#   3. On the pod: run THIS script. It pulls the corpus from R2 and extracts.
#   4. Copy the DB back down (now with features/timelines/labels):
#        scp root@<pod>:/workspace/creative-director/data/creative_director.db data/
#
# Pod prerequisites: repo cloned at /workspace/creative-director, .env present
# (R2_* creds), deps installed (pip install -r requirements.txt + the numpy<2 /
# sentence-transformers pins from the runpod workflow), rclone configured with
# an [r2] remote (see scripts/verify_r2.py docstring), nvidia-smi working.
set -euo pipefail

cd /workspace/creative-director
set -a; source .env; set +a   # load R2_BUCKET (+ other settings) for the rclone calls
NICHES=("ig_food" "ig_travel" "ig_fashion")

# --- pre-flight: fail fast instead of dying hours into the run ---
echo "== pre-flight =="
nvidia-smi -L || { echo "FATAL: no GPU visible (nvidia-smi) - grab another pod"; exit 1; }
# Real CUDA op, not just nvidia-smi: catches arch/CUDA mismatches (e.g. a 5090 /
# Blackwell sm_120 on an older torch, where nvidia-smi works but kernels don't).
python -c "import torch; assert torch.cuda.is_available(); ((torch.randn(64,64,device='cuda')@torch.randn(64,64,device='cuda')).sum().item()); print('torch CUDA OK:', torch.cuda.get_device_name(0))" \
  || { echo "FATAL: torch cannot use the GPU (CUDA/arch mismatch - Blackwell/5090 needs torch>=2.7 + cu128)"; exit 1; }
rclone listremotes | grep -q '^r2:' || { echo "FATAL: rclone [r2] remote missing - see verify_r2.py"; exit 1; }
python -c "from creative_director.storage import media; assert media.settings.r2_enabled" \
  || { echo "FATAL: R2_* not set in .env on the pod"; exit 1; }
echo "disk:"; df -h . | tail -1

# The niches were ingested on Windows, so video_file_path uses backslashes that
# don't resolve on Linux -> normalize to forward slashes (idempotent) or every
# video would be "not found" and extraction would silently no-op.
echo "== normalizing Windows paths in the DB =="
python -m scripts.normalize_paths

# Per-niche pull/extract/delete so a SMALL disk (e.g. 40GB) holds the corpus
# piecewise -- each niche's videos fit (food ~23GB, travel ~20GB, fashion ~9GB).
# If your pod disk is >=100GB, you can instead pull everything once up front:
#   rclone copy "r2:${R2_BUCKET}/videos" data/videos --transfers 16
# and delete the per-niche rclone/rm lines below.

# Parallelism: this pipeline is CPU-bound, so run several extractor processes
# across the vCPUs. Cap each worker's BLAS pools to 1 thread (process-level
# parallelism does the work) so 6 workers don't oversubscribe ~9 vCPU.
WORKERS="${WORKERS:-6}"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

for n in "${NICHES[@]}"; do
  echo "== [$n] pulling videos from R2 =="
  rm -rf data/videos && mkdir -p data/videos
  python -m scripts.list_niche_videos --niche "$n" --out "/tmp/${n}.txt"
  rclone copy "r2:${R2_BUCKET}/videos" data/videos \
    --files-from "/tmp/${n}.txt" --transfers 16 --progress
  echo "disk after pull:"; df -h . | tail -1

  echo "== [$n] feature extraction ($WORKERS parallel shards) =="
  pids=()
  for i in $(seq 0 $((WORKERS-1))); do
    python -m scripts.extract_features --niche "$n" --all-labeled --threads 1 --shard "$i/$WORKERS" \
      > "/workspace/feat_${n}_${i}.log" 2>&1 &
    pids+=("$!")
  done
  for p in "${pids[@]}"; do wait "$p" || echo "  feat shard $p exited non-zero"; done

  echo "== [$n] timeline extraction ($WORKERS parallel shards) =="
  pids=()
  for i in $(seq 0 $((WORKERS-1))); do
    python -m scripts.extract_timelines --niche "$n" --scope-niche "$n" --shard "$i/$WORKERS" \
      > "/workspace/tl_${n}_${i}.log" 2>&1 &
    pids+=("$!")
  done
  for p in "${pids[@]}"; do wait "$p" || echo "  tl shard $p exited non-zero"; done

  echo "== [$n] labels =="
  python -m scripts.compute_labels    --niche "$n"

  echo "== [$n] freeing disk for the next niche =="
  rm -rf data/videos/*
done

echo "== done. scp the DB back down, then terminate the pod. =="
