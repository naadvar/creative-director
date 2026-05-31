#!/usr/bin/env bash
# On-pod orchestration: Phase 1 (DB-only) gate + ML moves + desc embeddings.
# Designed for a CLEAN GPU pod (working torch -> sentence-transformers works,
# more RAM -> --compare won't OOM).
#
# Resilient by design: NO `set -e`. Each step is guarded so one failure can't
# abort the rest. PYTHONPATH exported so file-run + -m both import the package
# (no pyproject.toml on the pod).
#
#   nohup bash scripts/runpod_v3_run.sh > /workspace/v3_run.log 2>&1 &
set -uo pipefail

cd /workspace/creative-director
export PYTHONIOENCODING=utf-8
export PYTHONPATH=/workspace/creative-director:${PYTHONPATH:-}

PY=python3
NICHE=ig_fitness
LABEL=views_per_sub_aged_v1

echo "=== [1/5] description embedding backfill ($(date)) ==="
$PY -u scripts/backfill_description_embedding.py 2>&1 | tee v3_desc_embed.log \
  || echo "BACKFILL FAILED -- continuing with partial coverage"

echo "=== [2/5] full --compare gate ($(date)) ==="
$PY -m scripts.train_model --niche "$NICHE" --compare 2>&1 | tee v3_gate_compare.txt \
  || echo "GATE FAILED"

echo "=== [3/5] hyperparameter sweep ($(date)) ==="
$PY -m scripts.ml_moves sweep --niche "$NICHE" --label-scheme "$LABEL" --feature-set intrinsic 2>&1 | tee v3_sweep.txt \
  || echo "SWEEP FAILED"

echo "=== [4/5] multi-seed stability ($(date)) ==="
$PY -m scripts.ml_moves multiseed --niche "$NICHE" --label-scheme "$LABEL" --feature-set intrinsic 2>&1 | tee v3_multiseed.txt \
  || echo "MULTISEED FAILED"

echo "=== [5/6] model-family comparison ($(date)) ==="
$PY -m scripts.ml_moves family --niche "$NICHE" --label-scheme "$LABEL" --feature-set intrinsic 2>&1 | tee v3_family.txt \
  || echo "FAMILY FAILED"

echo "=== [6/6] naive baselines ($(date)) ==="
$PY -m scripts.ml_moves baselines --niche "$NICHE" --label-scheme "$LABEL" --feature-set intrinsic 2>&1 | tee v3_baselines.txt \
  || echo "BASELINES FAILED"

echo "=== ALL FINISHED ($(date)) ==="
