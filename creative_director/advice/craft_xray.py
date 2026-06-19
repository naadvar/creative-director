"""The Craft X-ray — a grounded, full-video craft READ of a reel.

This is the product's intelligence layer. From hi-res frames sampled across the whole
clip, one strong-VLM call returns: what the video IS, its structure (hook/payoff/pacing),
a one-line craft VERDICT, the single BIGGEST craft OPPORTUNITY, grounded BLIND SPOTS
(each with a concrete fix), and what's DONE WELL.

Honesty contract (hard): it plays to the VLM's proven strength — reading WHAT a video is
— and NEVER makes a performance/virality claim (the project proved nothing observable in
the reel predicts winning). "Better" means clearer / tighter / more watchable AS A VIDEO;
the creator decides if it's worth it. On-screen text is TRANSCRIBED FIRST (frames were
historically shrunk to 224px, making text illegible → "no text" hallucinations; we now
use hi-res individual frames + a forced transcribe-first field).

Returns None on any failure / no API key, so callers degrade gracefully.
"""
from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger

from creative_director.config import settings

SCHEMA_VERSION = 1


def _model() -> str:
    return getattr(settings, "craft_read_model", None) or "claude-opus-4-8"


# The MOAT SUBSTRATE: a closed treatment vocabulary. Every blind spot is tagged with a
# stable change_type so reads become machine-joinable — the left-hand side of a future
# advice->outcome pair (change_type x niche x format_class -> own-baseline delta). Free
# text is unjoinable; this enum is the thing the whole Bet-B flywheel depends on. Keep
# it CLOSED and stable; add a value only deliberately (a new value splits historical cells).
CHANGE_TYPES = [
    "hook_unclear",        # viewer can't tell what it's about in the first ~2s
    "dead_opening",        # wasted/blank/black/placeholder first frame
    "no_onscreen_text",    # topic / place / CTA lives only in the caption, nothing on screen
    "text_illegible",      # on-screen text too small / too fast / low-contrast to read
    "payoff_backloaded",   # the strongest / payoff shot is saved for the very end
    "payoff_missing",      # the hook promises something the video never shows
    "dead_time",           # a static / repeated stretch with no new information
    "weak_framing",        # subject small / off-center / obscured / poorly framed
    "wasted_ending",       # ends on black / watermark / a repeat instead of a strong beat
    "pacing_slow",         # overall too slow / shots held too long
    "other",               # a real craft note that fits none of the above
]

_CRAFT_TOOL = {
    "name": "report_craft",
    "description": "Report a grounded craft read + blind spots for a short-form reel.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["on_screen_text_found", "what_it_is", "format_class", "hook", "payoff",
                     "pacing", "verdict", "biggest_opportunity", "blind_spots", "change_types",
                     "done_well"],
        "properties": {
            "on_screen_text_found": {"type": "array", "items": {"type": "string"},
                "description": "STEP 1, FIRST: every piece of text visible on screen across all "
                "frames — overlays, captions, subtitles, signs, watermarks — each as 'm:ss - "
                "\"exact text\"'. IGNORE the small 'X.Xs' timestamp stamp in the very top-left "
                "corner — that is added by the tool, NOT the creator's text. Empty array ONLY if "
                "the creator put no text on screen. Never say 'no on-screen text' elsewhere unless "
                "this is empty."},
            "what_it_is": {"type": "string", "description": "1-2 plain sentences: what this video "
                "IS and what it's trying to do, as a viewer would summarize it. Grounded in frames."},
            "format_class": {"type": "string", "enum": ["talking_head", "visual_led", "mixed"],
                "description": "The reel's production format: talking_head (a person speaking to "
                "camera carries it), visual_led (b-roll / montage / demo, little or no talking), or "
                "mixed. A join key — be decisive."},
            "hook": {"type": "string", "description": "What the first ~2s shows, and at what "
                "timestamp a viewer first understands what the video is ABOUT. Cite a ts."},
            "payoff": {"type": "string", "description": "Is there a clear payoff/resolution to what "
                "the opening sets up? When does it land (ts)? Or is it missing / front-loaded / buried?"},
            "pacing": {"type": "string", "description": "One grounded note on pacing: any "
                "dead/static/repeated stretch (with timestamps), or 'steady throughout'."},
            "verdict": {"type": "string", "description": "ONE honest line judging the CRAFT of this "
                "video — what's strong and what holds it back as a piece of craft. Never a "
                "views/performance grade."},
            "biggest_opportunity": {"type": "string", "description": "The single highest-leverage "
                "CRAFT change for THIS video, and why — phrased as making it clearer/tighter/stronger. "
                "NEVER a claim it will get more views/reach/followers."},
            "blind_spots": {
                "type": "array", "maxItems": 4,
                "description": "Up to 4 self-evident craft observations the creator likely did NOT "
                "notice. Each ONE STRING shaped 'm:ss - [observation]. Fix: [a concrete editing change "
                "that makes it clearer/tighter/stronger]', grounded in a stamped frame. The Fix is a "
                "CRAFT change only — never a performance/views claim. Fewer (or none) if the reel is clean.",
                "items": {"type": "string"},
            },
            "change_types": {
                "type": "array",
                "description": "One tag PER blind_spot, IN THE SAME ORDER, from the closed "
                "vocabulary — the machine-readable treatment label. Same length as blind_spots.",
                "items": {"type": "string", "enum": CHANGE_TYPES},
            },
            "done_well": {"type": "array", "maxItems": 3, "items": {"type": "string"},
                "description": "Up to 3 genuine craft strengths, grounded in the frames."},
        },
    },
}

_SYSTEM = """You are an expert short-form video editor giving a creator a CRAFT READ of \
their Reel, from high-resolution frames sampled across the whole clip (each stamped with \
its timestamp, top-left). Tell them what their video IS, how it's STRUCTURED, where its \
BLIND SPOTS are, and how it could be BETTER — the craft things they're too close to notice.

STEP 1 — TRANSCRIBE TEXT FIRST (before any reasoning): read EVERY frame and list ALL \
on-screen text — title cards, caption overlays, subtitles, signs, watermarks — into \
on_screen_text_found, each with its timestamp. The frames are hi-res; read the small text. \
IGNORE the tiny 'X.Xs' stamp in the top-left corner (the tool added it). You may ONLY say \
'no on-screen text' if on_screen_text_found is genuinely empty. Do not under-report text.

RULES:
- Ground EVERY claim in what is literally visible in a stamped frame; cite timestamps.
- A blind spot is a SELF-EVIDENT craft observation the creator will recognize as true the \
moment they re-watch (e.g. "a viewer doesn't see what this is about until 0:04", "the \
finished dish is on screen by 0:02, then the video runs 20s more").
- NEVER claim anything about views, virality, reach, followers, the algorithm, or "doing \
better". You cannot predict performance and must not imply it. "hook"/"engaging"/"retention" \
only as plain craft description, never as a performance claim.
- Be specific and HONEST. Most reels have 2-4 genuine blind spots a sharp editor would \
name on a careful watch — surface them. Return fewer only when the reel is genuinely strong, \
and NEVER invent ones that aren't there.
- A faceless / voiceover / text-led reel is a LEGITIMATE format, never a flaw in itself.

THE INTELLIGENCE — say how it can be BETTER (this is the point of the tool):
- verdict: one honest line judging the craft of THIS video.
- biggest_opportunity: the single highest-leverage CRAFT change for THIS video, and why.
- every blind_spot ends with a concrete 'Fix:'.
- 'Better' = clearer / tighter / more watchable / more coherent AS A VIDEO. You may NEVER \
say or imply a change gets more views/reach/followers. Judge and improve the CRAFT only.

TAGGING (for internal aggregation, not shown to the creator): set format_class, and for \
EACH blind_spot output one change_types entry IN THE SAME ORDER from the closed vocabulary \
(hook_unclear, dead_opening, no_onscreen_text, text_illegible, payoff_backloaded, \
payoff_missing, dead_time, weak_framing, wasted_ending, pacing_slow, other). Pick the single \
best-fitting tag per blind spot; use 'other' only if none truly fit. change_types MUST be the \
same length as blind_spots."""


def _img(p: str) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
            "data": base64.standard_b64encode(Path(p).read_bytes()).decode("ascii")}}


def sample_frames_hires(mp4_path: str, out_dir: Path, n: int = 12, h: int = 720):
    """Sample n frames across the whole clip at HIGH resolution (h px tall) as INDIVIDUAL
    timestamp-stamped images — so on-screen text is legible to the VLM. Returns (paths, ts)."""
    import cv2

    cap = cv2.VideoCapture(str(mp4_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    nframes = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    dur = (nframes / fps) if nframes else 12.0
    ts = [round(dur * i / (n - 1), 2) for i in range(n)]
    out_dir.mkdir(parents=True, exist_ok=True)
    paths, kept = [], []
    for i, t in enumerate(ts):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(min(t, dur - 0.05) * fps))
        ok, fr = cap.read()
        if not ok:
            continue
        w = int(fr.shape[1] * h / fr.shape[0])
        fr = cv2.resize(fr, (w, h))
        label = f"{t:.1f}s"
        cv2.putText(fr, label, (12, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 7)
        cv2.putText(fr, label, (12, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)
        p = out_dir / f"f{i:02d}.jpg"
        cv2.imwrite(str(p), fr, [cv2.IMWRITE_JPEG_QUALITY, 90])
        paths.append(str(p))
        kept.append(t)
    cap.release()
    return paths, kept


_ARRAY_FIELDS = ("on_screen_text_found", "blind_spots", "change_types", "done_well")


def _use_openai() -> bool:
    """True when the craft read should hit an OpenAI-compatible endpoint (DeepInfra /
    OpenRouter / a vLLM pod serving Qwen2.5-VL) instead of Anthropic forced tool-use."""
    return bool(settings.craft_read_base_url and settings.craft_read_model
                and settings.craft_read_api_key)


def _incomplete(o: dict) -> bool:
    return not (o.get("verdict") and o.get("what_it_is") and o.get("blind_spots"))


def _data_uri(p: str) -> str:
    return "data:image/jpeg;base64," + base64.standard_b64encode(Path(p).read_bytes()).decode("ascii")


# OpenAI-compatible providers have no forced tool-use, so spell out the exact JSON shape.
_JSON_KEYS = (
    "Respond with ONLY one JSON object (no markdown fences, no prose) with EXACTLY these "
    'keys: "on_screen_text_found" (array of strings), "what_it_is" (string), "format_class" '
    '(one of "talking_head","visual_led","mixed"), "hook" (string), "payoff" (string), '
    '"pacing" (string), "verdict" (string), "biggest_opportunity" (string), "blind_spots" '
    '(array of strings, each "m:ss - observation. Fix: a concrete craft change"), '
    '"change_types" (array, ONE per blind_spot in the same order, each one of: '
    + ", ".join(CHANGE_TYPES) + '), "done_well" (array of strings). Strictly valid JSON: '
    "double-quote every key and string, no trailing commas, no raw newlines inside strings."
)


def _loads_robust(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        import re
        fixed = re.sub(r"[\x00-\x1f]",
                       lambda m: {"\n": "\\n", "\t": "\\t", "\r": ""}.get(m.group(), " "), s)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            logger.warning("craft_xray: unparseable JSON from openai-compatible provider")
            return None


def _call_anthropic(content, extra) -> Optional[dict]:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=_model(), max_tokens=3000, system=_SYSTEM,
        tools=[_CRAFT_TOOL], tool_choice={"type": "tool", "name": "report_craft"},
        messages=[{"role": "user", "content": content + (extra or [])}],
    )
    for b in resp.content:
        if b.type == "tool_use" and b.name == "report_craft":
            return dict(b.input)
    return None


def _call_openai(ctx: str, frames, extra: str) -> Optional[dict]:
    import httpx
    base = settings.craft_read_base_url.rstrip("/")
    user = ([{"type": "text", "text": ctx + extra}]
            + [{"type": "image_url", "image_url": {"url": _data_uri(p)}} for p in frames])
    body = {
        "model": settings.craft_read_model, "max_tokens": 3000, "temperature": 0,
        "messages": [{"role": "system", "content": _SYSTEM + "\n\n" + _JSON_KEYS},
                     {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
    }
    r = httpx.post(f"{base}/chat/completions", json=body, timeout=240,
                   headers={"Authorization": f"Bearer {settings.craft_read_api_key}"})
    r.raise_for_status()
    return _loads_robust(r.json()["choices"][0]["message"]["content"])


def craft_read_from_frames(frames: list[str], ts: list[float], *, niche=None,
                           caption=None, duration_s=None) -> Optional[dict]:
    """Strong-VLM craft read over hi-res frames. Routes to Anthropic (forced tool-use) or
    an OpenAI-compatible provider (Qwen2.5-VL via DeepInfra etc.) per config. Retries once
    if a load-bearing field is empty, then guarantees the keys exist."""
    openai = _use_openai()
    if not frames or (not openai and not settings.anthropic_api_key):
        return None
    ctx = (f"Context: niche={niche or 'unknown'}, duration={duration_s or '?'}s. "
           f"Caption opening: {json.dumps(caption or '')[:200]}. {len(frames)} high-res frames "
           f"span the whole clip; their stamped timestamps are: {ts}.")
    content = [{"type": "text", "text": ctx}] + [_img(p) for p in frames]
    _RETRY = ("Your previous output was incomplete. Return the FULL object with EVERY "
              "required field populated — especially verdict, what_it_is, and blind_spots "
              "(each with a Fix:) plus its matching change_types.")

    def one(retry: bool = False):
        if openai:
            return _call_openai(ctx, frames, ("\n\n" + _RETRY) if retry else "")
        return _call_anthropic(content, [{"type": "text", "text": _RETRY}] if retry else None)

    try:
        out = one()
        if out is not None and _incomplete(out):
            r2 = one(retry=True)
            if r2 and not _incomplete(r2):
                out = r2
        if out is None:
            logger.warning("craft_xray: no parseable craft read in response")
            return None
        for k in _ARRAY_FIELDS:  # never let a missing array break the card
            if not isinstance(out.get(k), list):
                out[k] = []
        # align the treatment tags to the blind spots (pad/truncate) so the moat join is
        # 1:1, and drop any tag outside the closed vocabulary.
        tags = [t if t in CHANGE_TYPES else "other" for t in out["change_types"]]
        nbs = len(out["blind_spots"])
        out["change_types"] = (tags + ["other"] * nbs)[:nbs]
        out["niche"] = niche            # join key for change_type x niche x format_class
        out["schema_version"] = SCHEMA_VERSION
        out["model"] = settings.craft_read_model if openai else _model()
        return out
    except Exception as e:  # noqa: BLE001 — never break the caller
        logger.warning(f"craft_xray call failed: {type(e).__name__}: {str(e)[:160]}")
    return None


def extract_craft_read(mp4_path: str, *, niche=None, caption=None,
                       duration_s=None) -> Optional[dict]:
    """Entry point: sample hi-res frames from the mp4 and return the craft-read dict."""
    if not (_use_openai() or settings.anthropic_api_key):
        return None
    with tempfile.TemporaryDirectory() as td:
        frames, ts = sample_frames_hires(mp4_path, Path(td))
        return craft_read_from_frames(frames, ts, niche=niche, caption=caption,
                                      duration_s=duration_s)
