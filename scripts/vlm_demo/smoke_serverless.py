"""Smoke-test the RunPod serverless vLLM endpoint before the real backfill.

Phase 1: a text request (confirms the server is up + auth works; absorbs the
first cold-start while the worker provisions and downloads the ~15GB model).
Phase 2: a synthetic image with distinctive shapes/text (confirms images are
actually being READ, not silently dropped — the LIMIT_MM_PER_PROMPT worry)."""
import base64
import io
import time

import httpx

from creative_director.config import settings

BASE = (settings.vlm_base_url or "").rstrip("/")
MODEL = settings.vlm_model
HEADERS = {"Authorization": f"Bearer {settings.vlm_api_key or 'EMPTY'}", "Content-Type": "application/json"}
print(f"endpoint: {BASE}")
print(f"model:    {MODEL}")


def chat(content, max_tokens=80, timeout=600.0):
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "user", "content": content}]}
    t = time.time()
    r = httpx.post(f"{BASE}/chat/completions", json=body, headers=HEADERS, timeout=timeout)
    dt = time.time() - t
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"], dt


print("\n=== Phase 1: warmup (text) — first call may take minutes (cold start + 15GB model download) ===")
try:
    txt, dt = chat("Reply with exactly: OK", max_tokens=10)
    print(f"  [{dt:.0f}s] {txt!r}")
except Exception as e:  # noqa: BLE001
    print(f"  FAILED: {type(e).__name__}: {str(e)[:400]}")
    raise SystemExit(1)

print("\n=== Phase 2: multimodal (does it READ the image?) ===")
from PIL import Image, ImageDraw  # noqa: E402

img = Image.new("RGB", (440, 200), "white")
d = ImageDraw.Draw(img)
d.ellipse([60, 50, 160, 150], fill="red")
d.rectangle([280, 50, 380, 150], fill="blue")
d.text((180, 165), "TEST 42", fill="black")
buf = io.BytesIO()
img.save(buf, format="JPEG")
uri = "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode()
content = [
    {"type": "text", "text": "Describe exactly what shapes, colors, and text you see in this image, in one sentence."},
    {"type": "image_url", "image_url": {"url": uri}},
]
try:
    txt, dt = chat(content, max_tokens=80)
    print(f"  [{dt:.0f}s] {txt!r}")
    low = txt.lower()
    hits = [w for w in ("red", "blue", "circle", "square", "rectangle", "42") if w in low]
    print(f"  matched image features: {hits}")
    if len(hits) >= 2:
        print("  RESULT: IMAGES ARE BEING READ — multimodal works.")
    else:
        print("  RESULT: output does NOT match the image — images may be dropped. STOP and investigate.")
except Exception as e:  # noqa: BLE001
    print(f"  FAILED: {type(e).__name__}: {str(e)[:400]}")
