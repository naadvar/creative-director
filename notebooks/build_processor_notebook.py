"""Generates colab_processor.ipynb — the GPU feature-extraction notebook.

Unlike colab_pipeline.ipynb (which ingests + downloads on Colab and needs a
proxy), this notebook extracts features from video files ALREADY downloaded
locally and shipped in colab_bundle.zip. No proxy, no YouTube API calls — pure
GPU feature + timeline extraction. Re-run this builder after editing the cells.
"""
import json
from pathlib import Path
from textwrap import dedent


def md(text: str) -> dict:
    text = dedent(text).strip("\n") + "\n"
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    text = dedent(text).strip("\n") + "\n"
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


cells = [
    md("""
        # Creative Director — Colab Feature Extraction (GPU)

        Extracts `VideoFeatures` + `VideoTimeline` for videos shipped in
        `colab_bundle.zip`. Runs CLIP / Whisper / audio / per-second timeline on
        the free T4 GPU — no proxy, no API calls, no downloading here.

        ## Before running
        1. Build the bundle locally: `python -m scripts.make_colab_bundle --niche fitness`
        2. Upload `data/colab_bundle.zip` to the **root of your Google Drive** (MyDrive).
        3. Runtime > Change runtime type > **T4 GPU**.
        4. Run the cells top to bottom. The bundle is unzipped to Colab's fast local
           disk — you do NOT need to unzip it on Drive yourself.
    """),

    md("## 1. System deps (Tesseract for OCR; ffmpeg is preinstalled)"),
    code("!apt-get -qq install -y tesseract-ocr"),

    md("## 2. Mount Google Drive"),
    code("""
        from google.colab import drive
        drive.mount('/content/drive')
    """),

    md("""
        ## 3. Unzip the bundle to local disk

        Working off the Drive FUSE mount is slow; we extract to Colab's local
        disk (`/content`) instead. Only the final processed DB is written back
        to Drive (last cell).
    """),
    code("""
        import os, sys, time, zipfile

        ZIP = '/content/drive/MyDrive/colab_bundle.zip'  # EDIT if you put it elsewhere
        assert os.path.isfile(ZIP), (
            f'{ZIP} not found. Upload colab_bundle.zip to the root of your Drive.'
        )

        PROJECT_DIR = '/content/creative-director'
        if not os.path.isdir(PROJECT_DIR) or not os.path.isdir(f'{PROJECT_DIR}/creative_director'):
            os.makedirs(PROJECT_DIR, exist_ok=True)
            print('Unzipping bundle to local disk...')
            t = time.time()
            with zipfile.ZipFile(ZIP) as z:
                z.extractall(PROJECT_DIR)
            print(f'Unzipped in {time.time() - t:.0f}s')
        else:
            print('Bundle already extracted, skipping.')

        sys.path.insert(0, PROJECT_DIR)
        os.chdir(PROJECT_DIR)
        print('Working in', PROJECT_DIR)
    """),

    md("""
        ## 4. Install Python dependencies
        Colab ships torch/opencv/numpy/pandas. First run ~5-10 min.
        `av` (PyAV) and `scenedetect` are required by the per-second timeline extractor.
    """),
    code("""
        !pip install -q \\
            faster-whisper \\
            librosa \\
            soundfile \\
            open-clip-torch \\
            sentence-transformers \\
            av \\
            scenedetect \\
            pytesseract \\
            yt-dlp \\
            SQLAlchemy \\
            pydantic pydantic-settings \\
            typer PyYAML python-dotenv httpx tenacity loguru tqdm scikit-learn
    """),

    md("""
        ## 5. Environment

        Everything lives on local disk now, so the DB, videos and thumbnails are
        all fast. `FORCE_CPU=false` so CLIP/Whisper use the GPU.
    """),
    code("""
        # Niche scope for this run. The IG corpus uses 'ig_fitness' but lacks
        # labels yet, so extract_features needs --all-labeled to include them.
        # extract_timelines is scoped via --scope-niche; --niche only picks
        # the CLIP prompt set, and fitness prompts work fine on fitness reels.
        NICHE = 'ig_fitness'
        CLIP_PROMPT_NICHE = 'fitness'

        os.environ['DATABASE_URL']    = f'sqlite:///{PROJECT_DIR}/data/creative_director.db'
        os.environ['VIDEO_ARCHIVE_DIR'] = f'{PROJECT_DIR}/data/videos'
        os.environ['THUMBNAIL_DIR']   = f'{PROJECT_DIR}/data/thumbnails'
        os.environ['TEMP_VIDEO_DIR']  = '/content/tmp'

        os.environ['FORCE_CPU']             = 'false'   # use the GPU
        os.environ['COOLDOWN_EVERY_N_VIDEOS'] = '0'     # no thermal cooldown needed on Colab
        os.environ['ENABLE_VIDEO_DOWNLOAD']   = 'true'  # idempotent: files already present, no real download
        os.environ['EXTRACT_VIDEO_FEATURES']  = 'true'
        os.environ['ENABLE_AUDIO_TRANSCRIPT'] = 'true'
        os.environ['ENABLE_CLIP_EMBEDDINGS']  = 'true'
        os.environ['ENABLE_FACE_DETECTION']   = 'true'
        os.environ['ENABLE_OCR']              = 'true'
        os.environ['WHISPER_MODEL']    = 'base'
        os.environ['CLIP_MODEL']       = 'ViT-B-32'
        os.environ['CLIP_PRETRAINED']  = 'laion2b_s34b_b79k'
        print('Env configured, niche =', NICHE)
    """),

    md("## 6. GPU sanity check"),
    code("""
        import torch
        print('CUDA available:', torch.cuda.is_available())
        if torch.cuda.is_available():
            print('Device:', torch.cuda.get_device_name(0))
        else:
            print('WARNING: no GPU. Runtime > Change runtime type > T4 GPU.')
    """),

    md("""
        ## 7. Feature extraction (CLIP + Whisper + audio + thumbnail)

        Resumable — videos that already have a `VideoFeatures` row are skipped, so
        re-running after a Colab disconnect just continues. `--threads 0` leaves
        the CPU uncapped (the laptop's thermal cap is irrelevant here).
        `--all-labeled` includes videos that don't have age-banded labels yet
        (needed for ig_fitness — labels will be computed locally after merge).
    """),
    code("!python -m scripts.extract_features --niche $NICHE --all-labeled --threads 0"),

    md("""
        ## 8. Per-second timeline extraction (PyAV + CLIP + PySceneDetect)

        Runs after feature extraction, which sets each video's file path. Also
        resumable — videos that already have timeline rows are skipped.
        `--scope-niche` filters which videos are processed; `--niche` selects
        the CLIP prompt set (fitness prompts work fine on IG fitness reels).
    """),
    code("!python -m scripts.extract_timelines --scope-niche $NICHE --niche $CLIP_PROMPT_NICHE"),

    md("## 9. Save the processed DB back to Drive"),
    code("""
        import shutil
        dst = '/content/drive/MyDrive/creative_director_processed.db'
        shutil.copy(f'{PROJECT_DIR}/data/creative_director.db', dst)
        print('Processed DB saved to', dst)
        print('Download it (or sync Drive) and run locally:')
        print('  python -m scripts.merge_features --source <path-to>/creative_director_processed.db')
    """),

    md("## 10. Stats"),
    code("""
        import sqlite3
        c = sqlite3.connect(f'{PROJECT_DIR}/data/creative_director.db')
        print('VideoFeatures rows :', c.execute('select count(*) from video_features').fetchone()[0])
        print('VideoTimeline rows :', c.execute('select count(*) from video_timeline').fetchone()[0])
        print('Videos timelined   :', c.execute('select count(distinct video_id) from video_timeline').fetchone()[0])
    """),

    md("""
        ## 11. Optional — remote bridge

        Lets Claude (on your local machine) drive/monitor this Colab session.
        Paste the printed `BRIDGE_URL` + `BRIDGE_TOKEN` into your local
        `C:\\Users\\naadv\\creative-director\\.colab_bridge` file, one per line.
        The token grants code execution here — don't share it.
    """),
    code("""
        !pip install -q fastapi 'uvicorn[standard]' pydantic httpx
        !wget -q -O /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
        !chmod +x /usr/local/bin/cloudflared
        print('bridge deps installed')
    """),
    code("""
        import threading, time, importlib, requests
        from colab_bridge import server as bridge_server
        importlib.reload(bridge_server)

        BRIDGE_PORT = 8765
        if not getattr(bridge_server, '_started', False):
            t = threading.Thread(
                target=bridge_server.start_server,
                kwargs={'host': '127.0.0.1', 'port': BRIDGE_PORT},
                daemon=True,
            )
            t.start()
            bridge_server._started = True
        for _ in range(30):
            try:
                requests.get(f'http://127.0.0.1:{BRIDGE_PORT}/openapi.json', timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        print(f'bridge up on 127.0.0.1:{BRIDGE_PORT}')
        print(f'BRIDGE_TOKEN={bridge_server.AUTH_TOKEN}')
    """),
    code("""
        import subprocess, re, atexit, threading

        proc = subprocess.Popen(
            ['cloudflared', 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{BRIDGE_PORT}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        atexit.register(proc.terminate)
        public_url = None
        for line in proc.stdout:
            print(line.rstrip())
            m = re.search(r'(https://[a-z0-9-]+\\.trycloudflare\\.com)', line)
            if m:
                public_url = m.group(1)
                break
        def _drain():
            for _ in proc.stdout:
                pass
        threading.Thread(target=_drain, daemon=True).start()
        print()
        print('=' * 60)
        print('Paste into C:\\\\Users\\\\naadv\\\\creative-director\\\\.colab_bridge')
        print('=' * 60)
        print(f'BRIDGE_URL={public_url}')
        print(f'BRIDGE_TOKEN={bridge_server.AUTH_TOKEN}')
    """),
]

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "colab": {"provenance": []},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = Path(__file__).parent / "colab_processor.ipynb"
out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print(f"Wrote {out}")
