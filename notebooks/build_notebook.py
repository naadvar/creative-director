"""Generates colab_pipeline.ipynb from a clean list of cells. Re-run after editing."""
import json
from pathlib import Path
from textwrap import dedent


def md(text: str) -> dict:
    text = dedent(text).strip("\n") + "\n"
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


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
        # Creative Director: Colab Pipeline

        Run the YouTube Shorts ingestion + feature extraction pipeline on Colab's free T4 GPU,
        with state persisted to Google Drive so sessions can disconnect and resume freely.

        ## Before running
        1. Copy the `creative-director` project to your Google Drive (use Google Drive for desktop
           on Windows, or upload the folder at drive.google.com).
        2. Update `PROJECT_DIR` below if the path differs.
        3. Have your **YouTube Data API v3 key** and **Decodo residential proxy URL** ready.
        4. Set the runtime to GPU: Runtime > Change runtime type > T4 GPU.
    """),

    md("## 1. System deps\nTesseract for thumbnail OCR. ffmpeg is preinstalled on Colab."),
    code("!apt-get -qq install -y tesseract-ocr"),

    md("## 2. Mount Google Drive"),
    code("""
        from google.colab import drive
        drive.mount('/content/drive')
    """),

    md("## 3. Project location\nAdjust `PROJECT_DIR` to wherever the `creative-director` folder lives in your Drive."),
    code("""
        import os, sys
        PROJECT_DIR = '/content/drive/MyDrive/creative-director'  # EDIT if your path differs
        assert os.path.isdir(PROJECT_DIR), (
            f'Project not found at {PROJECT_DIR}. Copy the folder to Drive first.'
        )
        sys.path.insert(0, PROJECT_DIR)
        os.chdir(PROJECT_DIR)
        print('Working in', PROJECT_DIR)
    """),

    md("""
        ## 4. Install Python dependencies
        Colab already has torch, opencv, numpy, pandas. We install the rest.
        First run takes ~5-10 minutes (CLIP weights, Whisper, MediaPipe).
    """),
    code("""
        !pip install -q \\
            google-api-python-client \\
            yt-dlp \\
            pytesseract \\
            faster-whisper \\
            librosa \\
            soundfile \\
            open-clip-torch \\
            sentence-transformers \\
            SQLAlchemy \\
            pydantic pydantic-settings \\
            typer PyYAML python-dotenv httpx tenacity loguru tqdm scikit-learn
    """),

    md("""
        ## 5. Credentials and paths

        Paste your keys here. For better practice, store them in Colab Secrets and read with
        `from google.colab import userdata; userdata.get('YOUTUBE_API_KEY')`.

        Decodo residential proxy URL format:
        `http://USER:PASS@gate.decodo.com:7000`
        (substitute your username/password from the Decodo dashboard)
    """),
    code("""
        # Required
        os.environ['YOUTUBE_API_KEY'] = ''   # paste your Data API v3 key
        os.environ['YTDLP_PROXY']     = ''   # paste your Decodo proxy URL

        # Persistent storage on Drive (survives disconnects)
        os.environ['DATABASE_URL']    = f'sqlite:///{PROJECT_DIR}/data/creative_director.db'
        os.environ['THUMBNAIL_DIR']   = f'{PROJECT_DIR}/data/thumbnails'

        # Ephemeral, fast — temp videos here, deleted immediately after extraction
        os.environ['TEMP_VIDEO_DIR']  = '/content/tmp'

        # Models
        os.environ['WHISPER_MODEL']    = 'base'           # 'small' for better quality, ~2x slower
        os.environ['CLIP_MODEL']       = 'ViT-B-32'
        os.environ['CLIP_PRETRAINED']  = 'laion2b_s34b_b79k'

        # Feature flags (turn off heavy steps for fast iteration)
        os.environ['ENABLE_VIDEO_DOWNLOAD']   = 'true'
        os.environ['ENABLE_AUDIO_TRANSCRIPT'] = 'true'
        os.environ['ENABLE_CLIP_EMBEDDINGS']  = 'true'
        os.environ['ENABLE_FACE_DETECTION']   = 'true'
        os.environ['ENABLE_OCR']              = 'true'

        assert os.environ['YOUTUBE_API_KEY'], 'YOUTUBE_API_KEY is required'
        if not os.environ['YTDLP_PROXY']:
            print('WARNING: YTDLP_PROXY is empty. Downloads will likely fail at volume from Colab.')
        print('Env configured')
    """),

    md("## 6. GPU sanity check"),
    code("""
        import torch
        print('CUDA available:', torch.cuda.is_available())
        if torch.cuda.is_available():
            print('Device:', torch.cuda.get_device_name(0))
        else:
            print('WARNING: no GPU. Switch runtime to T4 for ~10x speedup on CLIP + Whisper.')
    """),

    md("## 7. Initialize database"),
    code("""
        # Import after env vars are set so config.py picks them up
        from creative_director.storage.db import init_db
        init_db()
        print('DB initialized at', os.environ['DATABASE_URL'])
    """),

    md("""
        ## 8. Smoke test
        Pull 3 Shorts from one channel. If this completes without errors, the full
        pipeline (API + thumbnail + transient video + features) is working.
    """),
    code("""
        from creative_director.ingestion.pipeline import ingest_channel
        result = ingest_channel(channel_ref='@athleanx', niche='fitness', max_videos=3)
        print(result)
    """),

    md("""
        ## 9. Bulk ingest from a niche seed list

        Resumable: if your Colab session disconnects mid-run, just re-run this cell.
        Videos that already have features are skipped automatically.

        Tune `MAX_VIDEOS_PER_CHANNEL` based on time budget. Roughly:
        - 30 videos x 100 channels = 3000 videos
        - At ~45s/video on T4 + Decodo, that's ~37 hours of compute, or ~3-4 Colab sessions.
    """),
    code("""
        import yaml
        from tqdm.auto import tqdm

        NICHE = 'fitness'
        SEED_FILE = f'{PROJECT_DIR}/seed_channels/{NICHE}.yaml'
        MAX_VIDEOS_PER_CHANNEL = 30

        with open(SEED_FILE) as f:
            seed = yaml.safe_load(f) or {}

        channels = seed.get('channels', [])
        print(f'Ingesting {len(channels)} channels for niche={NICHE}, up to {MAX_VIDEOS_PER_CHANNEL} videos each')

        for ref in tqdm(channels, desc=NICHE):
            try:
                r = ingest_channel(
                    channel_ref=ref, niche=NICHE,
                    max_videos=MAX_VIDEOS_PER_CHANNEL,
                )
                print(r)
            except Exception as e:
                print(f'FAIL {ref}: {type(e).__name__}: {e}')
    """),

    md("## 10. Database stats"),
    code("""
        from sqlalchemy import select, func
        from creative_director.storage.db import session_scope
        from creative_director.storage.models import Channel, Video, VideoFeatures, VelocitySnapshot

        with session_scope() as s:
            print('Channels         :', s.scalar(select(func.count(Channel.id))))
            print('Videos (any)     :', s.scalar(select(func.count(Video.id))))
            print('Shorts           :', s.scalar(select(func.count(Video.id)).where(Video.is_short.is_(True))))
            print('Featurized videos:', s.scalar(select(func.count(VideoFeatures.video_id))))
            print('Velocity rows    :', s.scalar(select(func.count(VelocitySnapshot.id))))
    """),

    md("""
        ## 11. Re-poll velocity (run periodically)

        Adds a new `VelocitySnapshot` row for every video published within the window.
        Run this **every day or two** while you're building the dataset. The growth
        curves it produces are the basis for the virality label later.
    """),
    code("""
        from datetime import datetime, timedelta
        from sqlalchemy import select
        from creative_director.storage.models import Video, VelocitySnapshot
        from creative_director.youtube.client import get_youtube_client
        from creative_director.youtube.videos import fetch_videos

        MAX_AGE_DAYS = 45
        cutoff = datetime.utcnow() - timedelta(days=MAX_AGE_DAYS)

        with session_scope() as s:
            videos = s.execute(select(Video).where(Video.published_at >= cutoff)).scalars().all()
            ids = [v.id for v in videos]
            published_lookup = {v.id: v.published_at for v in videos}

        print(f'Re-polling stats for {len(ids)} videos')
        yt = get_youtube_client()
        added = 0
        for item in fetch_videos(yt, ids):
            vid = item['id']
            stats = item.get('statistics', {})
            published = published_lookup.get(vid)
            if not published:
                continue
            hours = (datetime.utcnow() - published).total_seconds() / 3600.0
            with session_scope() as s:
                s.add(VelocitySnapshot(
                    video_id=vid,
                    captured_at=datetime.utcnow(),
                    hours_since_publish=hours,
                    view_count=int(stats.get('viewCount', 0)),
                    like_count=int(stats['likeCount']) if 'likeCount' in stats else None,
                    comment_count=int(stats['commentCount']) if 'commentCount' in stats else None,
                    favorite_count=int(stats['favoriteCount']) if 'favoriteCount' in stats else None,
                ))
            added += 1
        print(f'Added {added} velocity snapshots')
    """),

    md("""
        ## 12. Optional: Remote bridge

        Start a tiny HTTP server in this Colab session, tunneled via cloudflared so
        Claude (running on your local machine) can drive experiments here directly.

        **Security:** the printed token grants full code execution in this Colab.
        Paste BRIDGE_URL and BRIDGE_TOKEN into your local
        `C:\\Users\\naadv\\creative-director\\.colab_bridge` file, one per line.
        Do not share publicly. The tunnel dies when Colab disconnects; re-run this
        cell to mint a fresh URL/token next session.
    """),
    code("""
        # 12a. Install bridge dependencies + cloudflared binary (once per session)
        !pip install -q fastapi 'uvicorn[standard]' pydantic httpx
        !wget -q -O /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
        !chmod +x /usr/local/bin/cloudflared
        print('bridge deps installed')
    """),
    code("""
        # 12b. Start the bridge server in a background thread
        import threading, time, importlib, requests
        from colab_bridge import server as bridge_server
        importlib.reload(bridge_server)  # picks up latest code if you edit it

        BRIDGE_PORT = 8765
        if not getattr(bridge_server, '_started', False):
            t = threading.Thread(
                target=bridge_server.start_server,
                kwargs={'host': '127.0.0.1', 'port': BRIDGE_PORT},
                daemon=True,
            )
            t.start()
            bridge_server._started = True

        # Wait for it to come up
        for _ in range(30):
            try:
                requests.get(f'http://127.0.0.1:{BRIDGE_PORT}/openapi.json', timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        print(f'bridge server up on 127.0.0.1:{BRIDGE_PORT}')
        print(f'BRIDGE_TOKEN={bridge_server.AUTH_TOKEN}')
    """),
    code("""
        # 12c. Open a Cloudflare ephemeral tunnel and parse the public URL
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

        # Keep draining stdout so cloudflared doesn't block on full pipe
        def _drain():
            for _ in proc.stdout:
                pass
        threading.Thread(target=_drain, daemon=True).start()

        print()
        print('=' * 60)
        print('Paste these two lines into your local')
        print('  C:\\\\Users\\\\naadv\\\\creative-director\\\\.colab_bridge')
        print('=' * 60)
        print(f'BRIDGE_URL={public_url}')
        print(f'BRIDGE_TOKEN={bridge_server.AUTH_TOKEN}')
    """),

    md("""
        ## Notes on sustained ingestion

        - **GPU runtime is essential** for CLIP + Whisper. CPU is ~10x slower.
        - **Throughput**: 30-90s per Shorts video on T4 + Decodo. A 12h Colab session
          handles 500-1500 videos.
        - **Free Colab caps**: ~12h session, idle disconnect after ~90 min. Re-run the
          bulk-ingest cell to resume; cached features are skipped.
        - **If yt-dlp errors with "Sign in to confirm you're not a bot"**: your proxy is
          missing or burnt. Verify `YTDLP_PROXY` is set; if it still fails, your Decodo
          allotment may be exhausted.
        - **Disk is ephemeral** (~80GB). Temp videos go to `/content/tmp` and are deleted
          immediately after feature extraction, so disk pressure stays near zero.
        - **More total volume**: ingest across multiple sessions on different days. This
          gives you time-diversity in the dataset and triggers more 24h/7d velocity
          snapshots on the same videos.
    """),
]


nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.11",
        },
        "colab": {"provenance": []},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


out = Path(__file__).parent / "colab_pipeline.ipynb"
out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print(f"Wrote {out}")
