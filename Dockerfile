# Serve-only backend image (Phase 1) — corpus browsing + benchmark advice.
# No torch/CLIP/Whisper: the ingest router is disabled via ENABLE_INGEST=false.
# The Phase-2 extraction worker uses the full requirements.txt in a separate image.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ENABLE_INGEST=false

# System libs needed by opencv-python-headless (libglib) and the BLAS/OpenMP
# used by numpy/scikit-learn (libgomp). No ffmpeg/libGL — extraction is disabled.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-serve.txt .
RUN pip install -r requirements-serve.txt

# Backend code only (the entrypoint fetches the corpus DB from R2 at boot).
COPY api ./api
COPY creative_director ./creative_director
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8000
CMD ["bash", "entrypoint.sh"]
