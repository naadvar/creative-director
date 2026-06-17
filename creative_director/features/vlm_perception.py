"""Full-video VLM perception — the grounded "WHAT is this reel" layer.

One Claude call over dense, timestamp-stamped frames spanning the WHOLE clip
returns a structured perception dict (canonical contract below). It is RELIABLE
at structural facts (genre / format / has_presenter / on-screen text) and is
held to CITED-ONLY craft observations; it is NOT trusted for causal "why it
performed" claims (those live in `hypothesis[]` and are gated downstream).

The single load-bearing field is ``has_presenter`` — the existing scalar advice
machinery already keys off presenter-state (see benchmark.py
face_advice_applies / _FACE_FEATS), so a bool maps cleanly onto the gate that
corrects the word-count archetype's one failure mode (mislabeling presenter
state — the genre miscategorizations that poison downstream advice).

Returns ``None`` on any failure / no API key, so callers fall back to the
scalar system with zero regression.
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

# Canonical contract — forced via tool-use so the model cannot return prose.
_PERCEPTION_TOOL = {
    "name": "report_perception",
    "description": "Report the structured perception of the reel's opening/whole clip.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "genre", "format", "has_presenter", "on_screen_text",
            "opening_shot", "observed", "hypothesis", "confidence",
        ],
        "properties": {
            "genre": {
                "type": ["string", "null"],
                "description": "Grounded archetype from the FRAMES, not a guess: one of "
                "talking_head, voiceover_animation, b_roll_demo, product_demo, "
                "faceless_montage, lifestyle_vlog, educational_tutorial, other. null if unclear.",
            },
            "format": {
                "type": ["string", "null"],
                "description": "Production style: single_take, montage, voiceover_with_text, "
                "talking_head, animation_heavy. null if unclear.",
            },
            "has_presenter": {
                "type": ["boolean", "null"],
                "description": "Is a human presenter on camera for a meaningful share of the clip? "
                "null only if genuinely uncertain. THIS DRIVES THE ADVICE GATE.",
            },
            "on_screen_text": {
                "type": ["string", "null"],
                "description": "Text visible in the first ~3s as one string (e.g. 'recipe title + "
                "ingredient list'). null if none.",
            },
            "opening_shot": {
                "type": ["string", "null"],
                "description": "1-2 sentences on the very first frame: framing, subject present?, "
                "dominant colors, anything wasted (e.g. a black frame).",
            },
            "observed": {
                "type": "array",
                "description": "CITED-ONLY static-frame facts. Each MUST cite a frame_ts equal to a "
                "stamped timestamp. Describe one frame — no motion/temporal verbs, no causal or "
                "outcome language. Each item is tagged with a 'kind' so it can be routed safely.",
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "frame_ts", "kind"],
                    "properties": {
                        "text": {"type": "string"},
                        "frame_ts": {"type": "number", "description": "a stamped timestamp in seconds"},
                        "kind": {
                            "type": "string",
                            "enum": ["opening_shot", "on_screen_text", "presence_of_person",
                                     "object_on_screen", "composition"],
                            "description": "what kind of WHAT-fact this is (closed vocabulary)",
                        },
                    },
                },
            },
            "hypothesis": {
                "type": "array",
                "description": "Craft patterns / risks (e.g. 'the hook promises a payoff the visual "
                "never shows'). May discuss craft, but NO guaranteed-outcome claims.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text"],
                    "properties": {"text": {"type": "string"}},
                },
            },
            "confidence": {
                "type": ["string", "null"],
                "enum": ["high", "medium", "low", None],
                "description": "Your confidence in genre + has_presenter.",
            },
        },
    },
}

_SYSTEM = """You are a short-form video strategist reading a creator's Instagram Reel \
from frames sampled across its whole timeline. Each frame is stamped with its \
timestamp in seconds (top-left). Report ONLY what you can literally see in a frame.

What to report:
- genre, format, has_presenter are STRUCTURAL FACTS — be decisive; null only if truly indeterminate.
- opening_shot: name what is in the VERY FIRST frame (0.0s) as static nouns/adjectives — \
subject present or not, framing, dominant colors, and explicitly whether the frame is WASTED \
(a black frame / logo bumper / title slate / blank). One frame only.
- on_screen_text: transcribe text visible in the first ~3s VERBATIM on a single line \
(replace line breaks with ' / '); null if none.
- observed: cited static-frame facts, each tagged with a 'kind' and a frame_ts from a stamp.

FORBIDDEN (these break the read):
- ANY motion or temporal verb (pushes, pans, zooms, reveals, then, cuts to, builds) — \
opening_shot and observed describe a SINGLE frame, not change between frames.
- ANY causal / outcome / performance word (hook, engaging, works, underperforms, 'this is why', \
'viewers will', boosts, hurts) anywhere except 'hypothesis'.
- Inventing text or objects not legible in a cited frame; aesthetic 'best moment' or 'should' language.
- Raw newlines inside any string value (use ' / ' instead) — they corrupt the output.

'hypothesis' may note craft patterns/risks but NEVER as guaranteed outcomes. You are reliable \
about WHAT the reel is; you are NOT a performance predictor."""


def _strip_from_frames(frames, out_path: Path) -> None:
    import cv2
    cv2.imwrite(str(out_path), cv2.hconcat(frames))


def sample_strips(mp4_path: str, out_dir: Path, n_frames: int = 4) -> tuple[list[str], list[float]]:
    """Sample n_frames evenly across the WHOLE clip, timestamp-stamp them, and
    write them as ceil(n/4) horizontal strips of 4. Returns (strip_paths, timestamps)."""
    import cv2

    cap = cv2.VideoCapture(str(mp4_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    nframes = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    dur = (nframes / fps) if nframes else 12.0
    ts = [round(dur * i / (n_frames - 1), 2) for i in range(n_frames)]
    frames = []
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(min(t, dur - 0.05) * fps))
        ok, fr = cap.read()
        if not ok:
            continue
        h = 224
        w = int(fr.shape[1] * h / fr.shape[0])
        fr = cv2.resize(fr, (w, h))
        cv2.putText(fr, f"{t:.1f}s", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(fr, f"{t:.1f}s", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        frames.append(fr)
    cap.release()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(0, len(frames), 4):
        chunk = frames[i:i + 4]
        p = out_dir / f"strip_{i // 4}.jpg"
        _strip_from_frames(chunk, p)
        paths.append(str(p))
    return paths, [t for t in ts][: len(frames)]


def _img_block(path: str) -> dict:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def _context_text(niche, caption, duration_s, timestamps) -> str:
    return (
        f"Context: niche={niche or 'unknown'}, duration={duration_s or '?'}s. "
        f"Caption opening: {json.dumps(caption or '')[:200]}. "
        f"The frames below span the whole clip; stamped timestamps"
        + (f" are among: {timestamps}." if timestamps else ".")
    )


def _perceive_anthropic(strip_paths, ctx, timestamps) -> Optional[dict]:
    api_key = settings.anthropic_api_key
    if not api_key:
        return None
    import anthropic

    content = [{"type": "text", "text": ctx}] + [_img_block(p) for p in strip_paths]
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=settings.vlm_model or settings.narrator_model,
        max_tokens=2500,
        system=_SYSTEM,
        tools=[_PERCEPTION_TOOL],
        tool_choice={"type": "tool", "name": "report_perception"},
        messages=[{"role": "user", "content": content}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "report_perception":
            out = dict(block.input)
            out["schema_version"] = SCHEMA_VERSION
            return out
    logger.warning("vlm_perception: no tool_use block in response")
    return None


def _lean_schema() -> dict:
    """Gate-critical fields ONLY (genre/format/has_presenter/confidence) — for the
    bulk corpus backfill. Drops the free-text fields (on_screen_text/opening_shot)
    too: the model puts reels' multi-line overlay text in them with raw newlines,
    which breaks JSON, and the gate doesn't need them. Tiny output = fast + robust.
    The full schema is reserved for per-upload Craft Reads."""
    s = _PERCEPTION_TOOL["input_schema"]
    drop = {"observed", "hypothesis", "on_screen_text", "opening_shot"}
    return {
        **s,
        "properties": {k: v for k, v in s["properties"].items() if k not in drop},
        "required": [r for r in s["required"] if r not in drop],
    }


def _perceive_openai_compatible(strip_paths, ctx, timestamps, lean=False) -> Optional[dict]:
    """Call a self-hosted vLLM (e.g. RunPod serving Qwen) or any OpenAI-style
    endpoint, forcing the (lean or full) schema via guided-JSON response_format."""
    import httpx

    base = (settings.vlm_base_url or "").rstrip("/")
    model = settings.vlm_model
    if not base or not model:
        logger.warning("vlm_perception: openai_compatible needs vlm_base_url + vlm_model")
        return None

    def data_uri(p):
        return "data:image/jpeg;base64," + base64.standard_b64encode(Path(p).read_bytes()).decode("ascii")

    content = [{"type": "text", "text": ctx}] + [
        {"type": "image_url", "image_url": {"url": data_uri(p)}} for p in strip_paths
    ]
    schema = _lean_schema() if lean else _PERCEPTION_TOOL["input_schema"]
    body = {
        "model": model,
        "max_tokens": 400 if lean else 900,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "report_perception", "schema": schema, "strict": True},
        },
    }
    headers = {"Authorization": f"Bearer {settings.vlm_api_key or 'EMPTY'}"}
    r = httpx.post(f"{base}/chat/completions", json=body, headers=headers, timeout=240)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    out = _loads_robust(content)
    if out is None:
        return None
    out["schema_version"] = SCHEMA_VERSION
    return out


def _loads_robust(content: str) -> Optional[dict]:
    """json.loads, with a fallback that escapes raw control chars inside string
    values (the model occasionally emits a raw newline in on_screen_text, which
    is invalid JSON). Returns None if it still can't parse."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        import re
        fixed = re.sub(r"[\x00-\x1f]", lambda m: {"\n": "\\n", "\t": "\\t", "\r": ""}.get(m.group(), " "), content)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            logger.warning("vlm_perception: unparseable JSON even after sanitize")
            return None


def perceive_from_strips(
    strip_paths: list[str],
    *,
    niche: Optional[str] = None,
    caption: Optional[str] = None,
    duration_s: Optional[int] = None,
    timestamps: Optional[list[float]] = None,
    lean: bool = False,
) -> Optional[dict]:
    """One VLM call over pre-rendered timestamped frame strips -> canonical
    perception dict (or None on any failure). Routes to the configured provider
    (Claude tool-use, or an OpenAI-compatible vLLM endpoint with guided JSON).

    ``lean=True`` (corpus backfill) returns structural fields only — far cheaper."""
    if not strip_paths:
        return None
    ctx = _context_text(niche, caption, duration_s, timestamps)
    try:
        if settings.vlm_provider == "openai_compatible":
            out = _perceive_openai_compatible(strip_paths, ctx, timestamps, lean=lean)
        else:
            out = _perceive_anthropic(strip_paths, ctx, timestamps)
        return _validate(out, timestamps) if out else None
    except Exception as e:  # noqa: BLE001 — never let perception break the upload job
        logger.warning(f"vlm_perception call failed: {type(e).__name__}: {str(e)[:160]}")
        return None


def _validate(out: dict, timestamps: Optional[list[float]]) -> dict:
    """Drop observed items whose frame_ts isn't a real sampled timestamp (the
    anti-temporal-hallucination rule). The full note verifier comes later."""
    if timestamps:
        allowed = {round(t, 1) for t in timestamps}
        kept = [o for o in (out.get("observed") or []) if round(float(o.get("frame_ts", -1)), 1) in allowed]
        out["observed_dropped"] = len(out.get("observed") or []) - len(kept)
        out["observed"] = kept
    return out


def extract_vlm_perception(
    mp4_path: str, *, niche: Optional[str] = None, caption: Optional[str] = None,
    duration_s: Optional[int] = None,
) -> Optional[dict]:
    """Pipeline entrypoint: sample frames from the mp4, run the VLM, return the
    canonical perception dict (None on failure). Stored on VideoFeatures.vlm_perception."""
    if not settings.anthropic_api_key:
        return None
    with tempfile.TemporaryDirectory() as td:
        strips, ts = sample_strips(mp4_path, Path(td))
        return perceive_from_strips(
            strips, niche=niche, caption=caption, duration_s=duration_s, timestamps=ts
        )
