"""Caption-as-remedy — one voice-matched caption suggestion, offered ONLY when the
read implicates the caption (never a standalone generator; the v1.2 judge panels
showed generic caption generation loses to creators' own writing, while the
remedy-context + texture-mimicry config passes).

Guarantees, same family as the rest of the read:
- Triggered by the read's own diagnosis (the word "caption" in the lever/notes),
  so the suggestion always has a reason to exist.
- Voice-matched to the creator's OWN past captions (texture: length/structure,
  emoji density, hashtag habits) — validated blind against real creators.
- Deterministic validators: no craft-note/production leakage, no performance
  language; one retry then honest absence (None), never filler.
"""
from __future__ import annotations

import re
from typing import Optional

from loguru import logger

from creative_director.config import settings

# Only offer a caption when the read itself talked about the caption.
_TRIGGER = re.compile(r"\bcaptions?\b", re.I)

# The suggestion must never reference our tooling / the diagnosis itself.
_LEAK = re.compile(
    r"\b(legib\w*|readab\w*|font size|text size|craft (?:read|note)|the app|this app)\b", re.I
)
# Performance-speak ban (same brand line as everywhere else).
_PERF = re.compile(
    r"\b(viral|virality|trending|algorithm|views|view count|followers|engagement|blow up|go viral)\b",
    re.I,
)

_SYSTEM = (
    "You are the same craft critic who just read this creator's reel; the read found a problem "
    "involving the caption, so you suggest the caption they should post instead. Ground ONLY in "
    "what is given: the transcript, the on-screen text, what the reel is, the craft note, and the "
    "creator's own PAST captions. "
    "VOICE — study the past captions and MIMIC THEIR TEXTURE, not just their tone: "
    "(a) LENGTH AND STRUCTURE: if they write multi-line instructional captions with numbered steps, "
    "write one of those; if they write five-word quips, write a five-word quip; match their "
    "line-break habits; (b) EMOJI: match their density and placement (none if they use none); "
    "(c) HASHTAGS and @mentions: match their count and placement habits exactly; (d) match their "
    "capitalization and punctuation quirks. The caption should be indistinguishable from their own "
    "writing. KEEP THEIR MISCHIEF: if their captions tease, joke, self-deprecate, or bait curiosity, "
    "yours must too — do not sand their edge off into polite ad copy; bland is a failure. A tease the "
    "reel PAYS OFF is great; a promise the reel doesn't keep is banned. HARD RULES: "
    "(1) NEVER mention the craft note, the app, text size, legibility, fonts, or anything about how "
    "the reel was made or improved — the caption is about the reel's CONTENT only; "
    "(2) never use a name or reference a new viewer could not understand from the reel itself, "
    "unless it appears in the creator's past captions; "
    "(3) if the reel withholds a reveal or payoff, the caption must NOT spoil it; "
    "(4) never performance language (viral, algorithm, engagement, followers, reach); "
    "(5) the first 100 characters must stand alone (that is what shows before '...more'); "
    "(6) TRANSCRIPT SPELLINGS ARE UNRELIABLE for names: transcripts are auto-generated audio, so "
    "never copy a brand, product, or person name from the transcript's spelling — only name a "
    "brand/person if that spelling appears in the creator's TYPED text (their captions). When "
    "unsure, leave the name out; a caption with no brand name beats one with a wrong brand name. "
    'Return ONLY JSON: {"caption": "...", "why": "one line on why this fits their voice"}'
)

_NO_HISTORY = (
    "The creator has no caption history yet — write in a neutral, casual creator voice matching "
    "the reel's tone, under 120 characters, at most one emoji, no hashtags."
)


def _call(system: str, user: str) -> Optional[dict]:
    import httpx

    from creative_director.advice.craft_xray import _loads_robust

    r = httpx.post(
        settings.craft_read_base_url.rstrip("/") + "/chat/completions",
        json={
            "model": settings.craft_read_model,
            "max_tokens": 400,
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
        headers={"Authorization": f"Bearer {settings.craft_read_api_key}"},
    )
    r.raise_for_status()
    return _loads_robust(r.json()["choices"][0]["message"]["content"])


def caption_implicated(read: dict) -> bool:
    """True when the read's own notes talk about the POST caption — the only time
    we offer a suggestion. "caption overlay"/"caption text" refer to on-screen
    text (a different remedy), so those phrasings are excluded first."""
    if not isinstance(read, dict):
        return False
    text = " ".join(
        [str(read.get("biggest_opportunity") or "")] + [str(b) for b in (read.get("blind_spots") or [])]
    )
    text = re.sub(r"\bcaptions?\s+(?:overlays?|text)\b", "", text, flags=re.I)
    return bool(_TRIGGER.search(text))


def _valid(out: Optional[dict], typed_sources: str = "") -> tuple[bool, str]:
    if not isinstance(out, dict) or not (out.get("caption") or "").strip():
        return False, "no caption produced"
    cap = str(out["caption"])
    if len(cap) > 1200:
        return False, "unreasonably long"
    m = _LEAK.search(cap)
    if m:
        return False, f"references the tooling/diagnosis ('{m.group(0)}')"
    m = _PERF.search(cap)
    if m:
        return False, f"performance language ('{m.group(0)}')"
    # @mentions must exist in the creator's TYPED text — an invented or
    # transcript-phonetic handle is a fabrication (judge-panel catch).
    src = typed_sources.lower()
    for h in re.findall(r"@[\w.]{2,}", cap):
        if h.lower() not in src:
            return False, f"mentions a handle not in their own captions ('{h}')"
    return True, ""


def suggest_caption(
    read: dict,
    *,
    transcript: Optional[str],
    current_caption: Optional[str],
    past_captions: list[str],
) -> Optional[dict]:
    """One voice-matched caption for a caption-implicated read, or None (honest
    absence). Caller decides persistence."""
    if not caption_implicated(read):
        return None
    voice = (
        "THE CREATOR'S PAST CAPTIONS (voice reference):\n- " + "\n- ".join(c[:220] for c in past_captions[:5])
        if len(past_captions) >= 1
        else _NO_HISTORY
    )
    user = (
        f"WHAT THE REEL IS: {str(read.get('what_it_is') or '')[:220]}\n"
        f"THE CRAFT NOTE THAT INVOLVES THE CAPTION: {str(read.get('biggest_opportunity') or '')[:240]}\n"
        f"ON-SCREEN TEXT: {[t for t in (read.get('on_screen_text_found') or [])[:6]]}\n"
        f"TRANSCRIPT (excerpt): {(transcript or '')[:600]}\n"
        f"THE CAPTION THEY CURRENTLY HAVE: {(current_caption or '(none)')[:240]}\n"
        f"{voice}\n\nWrite the one caption. JSON only."
    )
    typed = " ".join(past_captions) + " " + (current_caption or "")
    try:
        out = _call(_SYSTEM, user)
        ok, reason = _valid(out, typed)
        if not ok:
            logger.info(f"caption suggestion rejected (try 1): {reason}")
            out = _call(_SYSTEM, user + f"\n\nYour previous caption was rejected because: {reason}. Fix that.")
            ok, reason = _valid(out, typed)
        if not ok:
            logger.info(f"caption suggestion suppressed: {reason}")
            return None
        return {"text": str(out["caption"]).strip(), "why": str(out.get("why") or "").strip()[:160]}
    except Exception as e:  # noqa: BLE001 — provider failure -> honest absence
        logger.warning(f"caption suggestion failed: {type(e).__name__}")
        return None
