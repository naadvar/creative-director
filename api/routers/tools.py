"""Private TESTER utilities — not part of the product, never linked from the app.

/tools/reel-grab: paste an Instagram reel URL, get the mp4 to save to your phone,
so testers can try real reels without screen-recording them (screen recordings
lose the original audio track + add UI chrome, which skews the read).

Gated: routes 404 unless API_TOOLS_KEY is set, and require ?key=<API_TOOLS_KEY>.
Uses the same Apify path as the corpus ingestion (APIFY_API_TOKEN), via the
pay-per-result instagram-scraper actor (~fractions of a cent per reel). The
server downloads the mp4 from the (short-lived) CDN URL immediately and streams
it back, so the phone never touches the CDN link.
"""
from __future__ import annotations

import urllib.parse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from loguru import logger
from pydantic import BaseModel

from api.config import api_settings
from creative_director.config import settings

router = APIRouter(prefix="/tools", tags=["tools"])

_APIFY_SYNC = "https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items"
# The only hosts we'll download a reel from (Instagram/Facebook CDNs).
_ALLOWED_CDN_DOMAINS = ("cdninstagram.com", "fbcdn.net", "instagram.com")
_MAX_GRAB_BYTES = 300 * 1024 * 1024  # 300MB hard cap


def _gate(key: str | None) -> None:
    want = api_settings.tools_key
    if not want:
        raise HTTPException(status_code=404, detail="Not found")
    if (key or "") != want:
        raise HTTPException(status_code=403, detail="Bad key")


_PAGE = """<!doctype html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reel grabber — tester tool</title>
<style>
  body{background:#07070a;color:#f4f4f8;font-family:-apple-system,Segoe UI,Roboto,sans-serif;
       margin:0;padding:24px;display:flex;justify-content:center}
  .card{width:100%;max-width:480px}
  h1{font-size:20px;margin:8px 0}
  p{color:#8c8c9a;font-size:13px;line-height:1.5}
  input{width:100%;box-sizing:border-box;background:#131319;color:#f4f4f8;border:1px solid #2a2a36;
        border-radius:10px;padding:12px;font-size:15px;margin-top:12px}
  button{width:100%;margin-top:10px;padding:12px;border:0;border-radius:10px;font-weight:700;
         font-size:15px;color:#fff;background:linear-gradient(90deg,#7c5cff,#21c8ff)}
  button:disabled{opacity:.5}
  #status{margin-top:12px;font-size:13px;color:#8c8c9a;overflow-wrap:anywhere}
  video{width:100%;margin-top:14px;border-radius:12px;background:#000;display:none}
  a.dl{display:none;margin-top:10px;text-align:center;padding:12px;border-radius:10px;
       border:1px solid #2a2a36;color:#21c8ff;text-decoration:none;font-weight:600}
</style></head>
<body><div class="card">
  <h1>Reel grabber</h1>
  <p>Tester tool. Paste an Instagram reel link → fetch → save the mp4 to your phone →
     upload it in Creative Director. (Don't screen-record reels — recordings lose the real
     audio and add UI chrome, which skews the read.)</p>
  <input id="u" type="url" placeholder="https://www.instagram.com/reel/…" autocomplete="off">
  <button id="go" onclick="grab()">Fetch reel</button>
  <p id="status"></p>
  <video id="v" controls playsinline></video>
  <a id="dl" class="dl" download="reel.mp4">⬇︎ Save reel.mp4</a>
</div>
<script>
const KEY = new URLSearchParams(location.search).get('key') || '';
async function grab() {
  const u = document.getElementById('u').value.trim();
  const st = document.getElementById('status');
  const go = document.getElementById('go');
  if (!u) { st.textContent = 'Paste a reel link first.'; return; }
  go.disabled = true;
  st.textContent = 'Fetching — this takes ~20–60 seconds…';
  try {
    const r = await fetch('/tools/reel-grab/fetch', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: u, key: KEY}),
    });
    if (!r.ok) { st.textContent = 'Error: ' + (await r.text()); go.disabled = false; return; }
    const blob = await r.blob();
    const obj = URL.createObjectURL(blob);
    const v = document.getElementById('v'); const dl = document.getElementById('dl');
    v.src = obj; v.style.display = 'block';
    dl.href = obj; dl.style.display = 'block';
    st.textContent = 'Got it (' + (blob.size/1e6).toFixed(1) + ' MB). Tap Save, then upload it in the app.';
  } catch (e) { st.textContent = 'Failed: ' + e; }
  go.disabled = false;
}
</script></body></html>"""


@router.get("/reel-grab")
def reel_grab_page(key: str = "") -> HTMLResponse:
    _gate(key)
    return HTMLResponse(_PAGE)


@router.get("/users")
def users_list(key: str = "") -> Response:
    """Owner-only account list (key-gated like everything in /tools): email or
    connected platform, signup date, last login, upload count. This is the lead
    list for launch emails — treat the output as PII."""
    _gate(key)
    from sqlalchemy import select

    from creative_director.storage.db import session_scope
    from creative_director.storage.models import ConnectedAccount, Upload, User

    with session_scope() as s:
        users = s.execute(select(User).order_by(User.created_at)).scalars().all()
        upload_counts: dict[int, int] = {}
        for (uid,) in s.execute(select(Upload.user_id)).all():
            if uid is not None:
                upload_counts[uid] = upload_counts.get(uid, 0) + 1
        platforms: dict[int, str] = {}
        for conn in s.execute(select(ConnectedAccount)).scalars().all():
            platforms[conn.user_id] = conn.platform
        lines = [f"{'id':>4}  {'signed up':<12} {'last login':<12} {'uploads':>7}  identity"]
        for u in users:
            ident = u.email or f"[{platforms.get(u.id, 'no-email')}] {u.display_name or ''}".strip()
            lines.append(
                f"{u.id:>4}  {u.created_at.date() if u.created_at else '?':<12} "
                f"{u.last_login_at.date() if u.last_login_at else '?':<12} "
                f"{upload_counts.get(u.id, 0):>7}  {ident}"
            )
        lines.append(f"\ntotal: {len(users)}")
    return Response(content="\n".join(lines), media_type="text/plain; charset=utf-8")


@router.get("/kpis")
def kpis(key: str = "", format: str = "text") -> Response:
    """Live launch KPIs (WAU, retention cohorts, uploads funnel, suppression rate,
    helpful%, revision verdicts). Key-gated like the rest of /tools — check it from
    a phone at /tools/kpis?key=...&format=text."""
    _gate(key)
    from creative_director.storage.kpis import compute_kpis, render_text

    k = compute_kpis()
    if format == "json":
        import json as _json

        return Response(content=_json.dumps(k, indent=1), media_type="application/json")
    return Response(content=render_text(k), media_type="text/plain; charset=utf-8")


class GrabBody(BaseModel):
    url: str
    key: str = ""


@router.post("/reel-grab/fetch")
def reel_grab_fetch(body: GrabBody) -> Response:
    _gate(body.key)
    if not settings.apify_api_token:
        raise HTTPException(status_code=503, detail="APIFY_API_TOKEN isn't configured on the server")
    u = body.url.strip().split("?", 1)[0]
    if "instagram.com" not in u:
        raise HTTPException(status_code=422, detail="Paste an instagram.com reel/post URL")
    try:
        run = httpx.post(
            _APIFY_SYNC,
            params={"token": settings.apify_api_token, "timeout": 150, "memory": 1024},
            json={
                "directUrls": [u],
                "resultsType": "posts",
                "resultsLimit": 1,
                "addParentData": False,
            },
            timeout=180,
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Apify unreachable: {type(e).__name__}")
    if run.status_code >= 300:
        logger.warning(f"reel-grab: apify {run.status_code}: {run.text[:200]}")
        # Surface Apify's own message — e.g. "Too many outstanding invoices" (account
        # blocked) is actionable for us, where a bare 502 would just look broken.
        try:
            msg = run.json().get("error", {}).get("message") or f"Apify error {run.status_code}"
        except Exception:  # noqa: BLE001
            msg = f"Apify error {run.status_code}"
        raise HTTPException(status_code=502, detail=f"Apify: {msg}")
    items = run.json()
    video_url = None
    for it in items if isinstance(items, list) else []:
        video_url = it.get("videoUrl") or it.get("downloadedVideo")
        if video_url:
            break
    if not video_url:
        raise HTTPException(
            status_code=404, detail="No downloadable video found for that URL — is it a reel?"
        )
    # SSRF guard: the video URL comes from Apify's response, not the user — but treat
    # it as untrusted and only fetch from Instagram/Facebook CDNs, never an internal
    # address. (Prevents a poisoned response pointing at 169.254.169.254 etc.)
    host = (urllib.parse.urlparse(video_url).hostname or "").lower()
    if not any(host == d or host.endswith("." + d) for d in _ALLOWED_CDN_DOMAINS):
        logger.warning(f"reel-grab: refusing non-CDN host {host!r}")
        raise HTTPException(status_code=502, detail="Video URL wasn't a recognized Instagram CDN")
    # Stream with a hard size cap so a malicious/huge response can't exhaust memory.
    buf = bytearray()
    try:
        with httpx.stream("GET", video_url, timeout=120, follow_redirects=True) as media:
            if media.status_code != 200:
                raise HTTPException(status_code=502, detail="Couldn't download the video from the CDN — try again")
            for chunk in media.iter_bytes():
                buf.extend(chunk)
                if len(buf) > _MAX_GRAB_BYTES:
                    raise HTTPException(status_code=502, detail="Reel is unexpectedly large — aborting")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"CDN download failed: {type(e).__name__}")
    if len(buf) < 50_000:
        raise HTTPException(status_code=502, detail="Couldn't download the video from the CDN — try again")
    logger.info(f"reel-grab: served {u} ({len(buf)/1e6:.1f} MB)")
    return Response(
        content=bytes(buf),
        media_type="video/mp4",
        headers={"Content-Disposition": 'attachment; filename="reel.mp4"'},
    )
