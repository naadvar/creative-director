"""'Ideas from your DNA' — grounded reel ideation, the answer to "what should I
make next?".

The bar (see docs/IDEAS_FEATURE.md): if a generic LLM with no context could produce
the idea, it must not ship. Mechanisms:
- Ideas are generated ONLY from (a) the creator's own grounded reads and (b) an
  aggregate craft digest of their niche corpus — never trends, never performance.
- Every idea must cite real video_ids from the creator's own uploads; a
  deterministic validator rejects fabricated citations, trend/performance speak,
  model-authored statistics, remixes of reels they already made, and a wrong gap.
- All numbers shown to the creator (gap stats, corpus percentages) are composed
  server-side from fingerprint/progress/digest — the model is forbidden from
  writing statistics, so the most personalized lines carry zero fabrication surface.
- One retry with the rejection reasons, then an honest empty state — the same
  say-nothing-over-invent contract as the grounding gate.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Optional

from loguru import logger
from sqlalchemy import select

from creative_director.config import settings
from creative_director.profile.fingerprint import _CHANGE_FRIENDLY, compute_fingerprint
from creative_director.profile.progress import DIM_LABEL, compute_progress
from creative_director.storage.db import session_scope
from creative_director.storage.models import (
    Channel,
    CreatorIdea,
    Upload,
    Video,
    VideoFeatures,
)

DAILY_IDEA_CAP = 5  # generations per user per UTC day (cache hits don't count)


# ---------------------------------------------------------------- creator DNA
def _creator_dna(user_id: int) -> dict:
    """The creator's grounded reads (newest 5) + fingerprint/progress aggregates +
    the single craft gap this idea must pre-empt. Everything the prompt needs."""
    with session_scope() as s:
        rows = (
            s.execute(
                select(Upload)
                .where(Upload.user_id == user_id, Upload.craft_read.isnot(None))
                .order_by(Upload.created_at.desc())
            )
            .scalars()
            .all()
        )
        reads = []
        for u in rows:
            r = u.craft_read
            if not isinstance(r, dict) or r.get("grounded") is False:
                continue
            reads.append(
                {
                    "video_id": u.video_id,
                    "niche": u.niche,
                    "title": (u.title or "")[:80],
                    "date": u.created_at.date().isoformat() if u.created_at else "",
                    "what_it_is": (r.get("what_it_is") or "").strip()[:160],
                    "done_well": [d for d in (r.get("done_well") or []) if isinstance(d, str)][:3],
                    "change_types": [c for c in (r.get("change_types") or []) if isinstance(c, str)],
                    "dimension": (r.get("opportunity_dimension") or "").strip(),
                    "format_class": r.get("format_class") or "",
                }
            )

    n = len(reads)
    ids = [r["video_id"] for r in reads]
    cache_key = hashlib.sha1(",".join(sorted(ids)).encode()).hexdigest()[:16]
    fp = compute_fingerprint(user_id)
    prog = compute_progress(user_id)

    # The gap to pre-empt: recurring change_type (3+ reads) > recurring dimension >
    # the latest read's note (1-2 reads, watch-item framing) > none (clean DNA).
    gap_key, gap_label, gap_count, gap_tier = "none", "", 0, "none"
    fp_rec = fp.get("recurring") or []
    pr_rec = prog.get("recurring") or []
    if n >= 3 and fp_rec:
        gap_key = fp_rec[0]["type"]
        gap_label = fp_rec[0]["label"]
        gap_count = fp_rec[0]["count"]
        gap_tier = "recurring"
    elif n >= 3 and pr_rec:
        gap_key = pr_rec[0]["dimension"]
        gap_label = pr_rec[0]["label"]
        gap_count = pr_rec[0]["count"]
        gap_tier = "recurring"
    elif n >= 1:
        last = reads[0]
        if last["change_types"]:
            gap_key = last["change_types"][0]
            gap_label = _CHANGE_FRIENDLY.get(gap_key, gap_key)
            gap_tier = "watch"
        elif last["dimension"] and last["dimension"] != "none":
            gap_key = last["dimension"]
            gap_label = DIM_LABEL.get(last["dimension"], last["dimension"])
            gap_tier = "watch"

    return {
        "n": n,
        "reads": reads[:5],
        "ids": set(ids),
        "cache_key": cache_key,
        "niche": fp.get("niche") or (reads[0]["niche"] if reads else None),
        "format": fp.get("format") or "",
        "gap_key": gap_key,
        "gap_label": gap_label,
        "gap_count": gap_count,
        "gap_tier": gap_tier,
    }


# ------------------------------------------------------------- niche digest
@lru_cache(maxsize=8)
def _niche_digest(niche: str, fmt: str) -> Optional[dict]:
    """Aggregate craft patterns for the niche, computed once per process from the
    read-only corpus: change_type prevalence (real percentages) + a few structure
    exemplars from CLEAN reels of the creator's dominant format. PROMPT-ONLY input —
    aggregate lines may reach the screen, corpus content itself never does."""
    try:
        with session_scope() as s:
            rows = (
                s.execute(
                    select(VideoFeatures.craft_read)
                    .join(Video, Video.id == VideoFeatures.video_id)
                    .join(Channel, Channel.id == Video.channel_id)
                    .where(Channel.niche == niche, VideoFeatures.craft_read.isnot(None))
                )
                .scalars()
                .all()
            )
    except Exception as e:  # noqa: BLE001 — a digest failure must never block ideation
        logger.warning(f"niche digest failed for {niche}: {type(e).__name__}")
        return None
    grounded = [r for r in rows if isinstance(r, dict) and r.get("grounded") is not False]
    n = len(grounded)
    if n < 50:
        return None
    from collections import Counter

    counts: Counter = Counter()
    for r in grounded:
        for t in set(r.get("change_types") or []):
            if t and t != "other":
                counts[t] += 1
    top = [(t, round(100 * c / n)) for t, c in counts.most_common(3)]
    exemplars = []
    for r in grounded:
        if not (r.get("blind_spots") or []) and (r.get("format_class") or "") == fmt:
            w = (r.get("what_it_is") or "").strip()
            if w:
                exemplars.append(w[:160])
        if len(exemplars) >= 10:
            break
    return {"n": n, "top": top, "exemplars": exemplars}


# ------------------------------------------------------------------ the call
_SYSTEM = """You are the same craft critic who wrote this creator's reel reads — now planning their NEXT reel. Produce ONE concrete, shootable reel concept grounded ONLY in (a) the creator's own reels and craft notes and (b) aggregate craft patterns for their niche, both given below.
HARD RULES:
- CITE: grounded_in and strength_used must reference video_ids from the CREATOR DNA list. Every video_id you write MUST appear in that list — never invent a reel.
- CRAFT, NEVER PERFORMANCE: never mention views, reach, followers, engagement, virality, trends, trending audio, challenges, or the algorithm. The idea is judged as craft — clearer, tighter, more watchable — never as performance.
- NO NUMBERS: write no statistics, counts, or percentages anywhere; the app attaches real ones itself.
- PRE-EMPT THE GAP: structure the beat_sheet so the creator's TOP CRAFT GAP cannot recur — plan the fix into the shoot itself (e.g. gap text_illegible: specify where the text sits, how large, how long it holds, before they shoot).
- NEW, NOT A REMIX: the concept must not restate any reel in the CREATOR DNA list. Build on a strength; don't repeat a video.
- SHOOTABLE: phone-camera realistic, one or two sessions, no crew.
- NICHE-BOUND: if the concept would read as a fine suggestion for any creator in any niche, it is wrong. It must only make sense for THIS creator's niche, format, and strengths.
Respond with ONLY one JSON object (no markdown fences, no prose) with EXACTLY these keys: "concept" (string, <=10 words), "premise" (string, 1-2 sentences), "format" (one of "talking_head","visual_led","mixed"), "grounded_in" (array of 1-2 objects {"video_id","why"}), "strength_used" (object {"video_id","strength","how"}), "beat_sheet" (array of 3-5 objects {"beat","time","direction"}, times as m:ss ranges), "gap_guardrail" (object {"gap": exactly the gap key given below, "plan": string}), "shoot_notes" (string, one line). Strictly valid JSON."""


def _build_user(dna: dict, digest: Optional[dict]) -> str:
    lines = ["CREATOR DNA (their real reels — the ONLY legal video_ids to cite):"]
    for r in dna["reads"]:
        notes = ", ".join(r["change_types"]) or "clean"
        dw = "; ".join(r["done_well"][:2]) or "-"
        lines.append(
            f"- {r['video_id']} ({r['date']}, {r['format_class'] or '?'}): {r['what_it_is'] or r['title']}"
            f" | done_well: {dw} | notes: [{notes}]"
        )
    niche_word = (dna.get("niche") or "short-form").replace("ig_", "")
    lines.append(f"Dominant format: {dna['format'] or 'unknown'}. Niche: {niche_word}.")

    if dna["gap_tier"] == "recurring":
        lines.append(
            f"\nTOP CRAFT GAP TO PRE-EMPT — \"{dna['gap_key']}\" ({dna['gap_label']}): recurred across their reads."
        )
    elif dna["gap_tier"] == "watch":
        lines.append(
            f"\nTOP CRAFT GAP TO PRE-EMPT — \"{dna['gap_key']}\" ({dna['gap_label']}): came up in their last read; treat it as a watch-item, not a pattern."
        )
    else:
        lines.append(
            "\nTOP CRAFT GAP TO PRE-EMPT — \"none\": their reads are clean; the guardrail should reinforce their strongest habit instead."
        )

    strengths = []
    for r in dna["reads"]:
        for d in r["done_well"][:1]:
            strengths.append(f"- {r['video_id']}: {d}")
        if len(strengths) >= 2:
            break
    if strengths:
        lines.append("\nSTRENGTHS TO LEAN ON:")
        lines.extend(strengths)

    if digest:
        pct = ", ".join(f"{t} {p}%" for t, p in digest["top"])
        lines.append(
            f"\nNICHE CRAFT DIGEST (background knowledge — never name, quote, or reference any specific reel "
            f"from this digest in your output): most common craft notes in {niche_word} "
            f"(share of {digest['n']} analyzed reels): {pct}."
        )
        if digest["exemplars"]:
            lines.append("Structure exemplars from clean reels of their format:")
            lines.extend(f"- {e}" for e in digest["exemplars"])

    lines.append("\nTASK: Give ONE idea for their next reel. JSON only.")
    return "\n".join(lines)


def _call_llm(system: str, user: str) -> Optional[dict]:
    import httpx

    from creative_director.advice.craft_xray import _loads_robust

    base = settings.craft_read_base_url.rstrip("/")
    body = {
        "model": settings.craft_read_model,
        "max_tokens": 900,
        "temperature": 0.9,  # ideation needs variety; the validator makes this safe
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    r = httpx.post(
        f"{base}/chat/completions",
        json=body,
        timeout=120,
        headers={"Authorization": f"Bearer {settings.craft_read_api_key}"},
    )
    r.raise_for_status()
    return _loads_robust(r.json()["choices"][0]["message"]["content"])


# ----------------------------------------------------------------- validator
_VID_RE = re.compile(r"up_[0-9a-f]{12}")
# Performance/trend-speak is banned OUTPUT, not just banned input. "reach" only in
# its performance collocations (fitness beats legitimately say "reach overhead").
_BANNED = re.compile(
    r"\b(viral|virality|trending|trend audio|algorithm|views|view count|followers|"
    r"engagement|blow up|go viral|day in the life|top \d+|you won'?t believe|challenge)\b"
    r"|\b(your|more|max(?:imize)?|boost(?:ing)?|audience|wider|broader) reach\b",
    re.I,
)
# Ban model-authored POPULATION statistics (fake corpus claims) — "37% of reels",
# "most creators", "8 in 10 videos". Spatial craft directions ("text at 80% width",
# "hold at 100% zoom") are legitimate and allowed.
_POP = r"(?:all\s+)?(?:reels|videos|shorts|creators|viewers|accounts|people|posts|users)"
_MODEL_STATS = re.compile(
    rf"\d\s*%\s*of\s+{_POP}\b|\bpercent\s+of\s+{_POP}\b"
    rf"|\b\d+\s+(?:of|in)\s+\d+\s+{_POP}\b|\bmost creators\b|\banalyzed reels\b",
    re.I,
)
_FORMATS = {"talking_head", "visual_led", "mixed"}


def _idea_text(idea: dict) -> str:
    parts = [str(idea.get("concept", "")), str(idea.get("premise", ""))]
    for b in idea.get("beat_sheet") or []:
        if isinstance(b, dict):
            parts += [str(b.get("beat", "")), str(b.get("direction", ""))]
    gg = idea.get("gap_guardrail") or {}
    parts.append(str(gg.get("plan", "")) if isinstance(gg, dict) else str(gg))
    parts.append(str(idea.get("shoot_notes", "")))
    return " ".join(parts)


def _validate(idea: Optional[dict], dna: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not isinstance(idea, dict):
        return False, ["no parseable JSON object"]
    # (a) shape
    for k in ("concept", "premise", "format", "grounded_in", "strength_used",
              "beat_sheet", "gap_guardrail", "shoot_notes"):
        if k not in idea:
            reasons.append(f"missing key {k}")
    if idea.get("format") not in _FORMATS:
        reasons.append("format not one of talking_head|visual_led|mixed")
    beats = idea.get("beat_sheet")
    if not isinstance(beats, list) or not (3 <= len(beats) <= 5):
        reasons.append("beat_sheet must have 3-5 beats")
    grounded_in = idea.get("grounded_in")
    if not isinstance(grounded_in, list) or not grounded_in:
        reasons.append("grounded_in must cite at least one of the creator's reels")
    # (b) citations must be real
    cited = set(_VID_RE.findall(json.dumps(idea)))
    fake = cited - dna["ids"]
    if fake:
        reasons.append(f"cites reels that don't exist: {sorted(fake)}")
    if not cited:
        reasons.append("no video_id citations found")
    text = _idea_text(idea)
    # (c) trend/performance speak
    m = _BANNED.search(text)
    if m:
        reasons.append(f"banned performance/trend language: '{m.group(0)}'")
    # (d) model-authored statistics
    m = _MODEL_STATS.search(text)
    if m:
        reasons.append(f"model-authored statistic: '{m.group(0)}' (numbers are server-stamped only)")
    # (e) remix rejection
    premise = str(idea.get("premise", ""))
    for r in dna["reads"]:
        if r["what_it_is"] and difflib.SequenceMatcher(
            None, premise.lower(), r["what_it_is"].lower()
        ).ratio() > 0.6:
            reasons.append(f"restates their existing reel {r['video_id']}")
            break
    # (f) gap echo
    gg = idea.get("gap_guardrail")
    if not (isinstance(gg, dict) and (gg.get("gap") or "").strip() == dna["gap_key"]):
        reasons.append(f"gap_guardrail.gap must be exactly '{dna['gap_key']}'")
    return (not reasons), reasons


# ------------------------------------------------------------------ envelope
def _stat_lines(dna: dict, digest: Optional[dict]) -> tuple[str, Optional[str]]:
    n = dna["n"]
    if dna["gap_tier"] == "recurring":
        gap_stat = f"{dna['gap_label'].capitalize()} came up in {dna['gap_count']} of your {n} reads."
    elif dna["gap_tier"] == "watch":
        gap_stat = f"In your last read, the note was {dna['gap_label']} — one to watch."
    else:
        gap_stat = f"No recurring craft note across your {n} read{'s' if n != 1 else ''} — this idea leans on your strengths."
    digest_line = None
    if digest and dna["gap_key"] not in ("", "none"):
        for rank, (t, p) in enumerate(digest["top"], 1):
            if t == dna["gap_key"]:
                niche_word = (dna.get("niche") or "your niche").replace("ig_", "")
                label = _CHANGE_FRIENDLY.get(t, t)
                digest_line = (
                    f"It's also the #{rank} note in {niche_word} — {p}% of {digest['n']:,} analyzed reels."
                )
                break
    return gap_stat, digest_line


def _envelope(row: CreatorIdea, dna: dict, digest: Optional[dict]) -> dict:
    gap_stat, digest_line = _stat_lines(dna, digest)
    cited = list(dict.fromkeys(_VID_RE.findall(json.dumps(row.idea))))
    citations = []
    with session_scope() as s:
        for vid in cited:
            u = s.get(Upload, vid)
            citations.append(
                {
                    "video_id": vid,
                    "title": (u.title if u else None) or "Your reel",
                    "thumbnail_url": f"/api/videos/{vid}/thumbnail",
                }
            )
    out = {
        "ready": True,
        "n_reads": dna["n"],
        "idea": row.idea,
        "idea_id": row.id,
        "generated_at": row.created_at.isoformat() if row.created_at else None,
        "gap_stat_line": gap_stat,
        "digest_line": digest_line,
        "citations": citations,
        "feedback": row.feedback,
    }
    if dna["n"] < 3:
        out["caveat"] = (
            f"Built from only {dna['n']} read{'s' if dna['n'] != 1 else ''} — your DNA is still forming."
        )
    return out


# ------------------------------------------------------------------- compute
def compute_idea(user_id: int, fresh: bool = False) -> dict:
    """One grounded idea for the creator's next reel. Cached per DNA state (a new
    grounded read changes cache_key -> fresh idea). `fresh` forces a regeneration,
    capped at DAILY_IDEA_CAP/day. Honest empty state over filler, always."""
    dna = _creator_dna(user_id)
    if dna["n"] == 0:
        return {
            "ready": False,
            "n_reads": 0,
            "reason": "Read a reel first — ideas are built from your own reads.",
        }
    from creative_director.advice.craft_xray import _use_openai

    if not _use_openai():
        return {"ready": False, "n_reads": dna["n"], "reason": "Idea engine isn't configured."}

    digest = _niche_digest(dna.get("niche") or "", dna["format"]) if dna.get("niche") else None

    with session_scope() as s:
        if not fresh:
            row = (
                s.execute(
                    select(CreatorIdea)
                    .where(
                        CreatorIdea.user_id == user_id,
                        CreatorIdea.cache_key == dna["cache_key"],
                    )
                    .order_by(CreatorIdea.created_at.desc())
                )
                .scalars()
                .first()
            )
            if row is not None:
                return _envelope(row, dna, digest)
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today = (
            s.execute(
                select(CreatorIdea.id).where(
                    CreatorIdea.user_id == user_id, CreatorIdea.created_at >= day_start
                )
            )
            .scalars()
            .all()
        )
        if len(today) >= DAILY_IDEA_CAP:
            return {
                "ready": False,
                "capped": True,
                "n_reads": dna["n"],
                "reason": "Daily idea limit reached — fresh ideas tomorrow.",
            }

    system, user = _SYSTEM, _build_user(dna, digest)
    # "Show me another" should actually be another: tell the model what it already
    # proposed for this DNA state so regenerates explore, not orbit.
    with session_scope() as s:
        prior_concepts = [
            str((r.idea or {}).get("concept", "")).strip()
            for r in s.execute(
                select(CreatorIdea)
                .where(CreatorIdea.user_id == user_id, CreatorIdea.cache_key == dna["cache_key"])
                .order_by(CreatorIdea.created_at.desc())
            ).scalars().all()
        ]
    prior_concepts = [c for c in prior_concepts if c][:5]
    if prior_concepts:
        user += (
            "\n\nALREADY PROPOSED (do NOT repeat or lightly rephrase these — take a genuinely "
            "different angle): " + "; ".join(prior_concepts)
        )
    idea, reasons = None, ["not generated"]
    try:
        idea = _call_llm(system, user)
        ok, reasons = _validate(idea, dna)
        if not ok:
            logger.info(f"idea rejected for user {user_id} (try 1): {reasons}")
            retry_user = (
                user
                + "\n\nYour previous idea was rejected because: "
                + "; ".join(reasons)
                + ". Produce a corrected idea that violates none of the rules."
            )
            idea = _call_llm(system, retry_user)
            ok, reasons = _validate(idea, dna)
    except Exception as e:  # noqa: BLE001 — provider failure -> honest empty state
        logger.warning(f"idea generation failed for user {user_id}: {type(e).__name__}: {str(e)[:120]}")
        ok = False
    if not ok:
        logger.info(f"idea suppressed for user {user_id}: {reasons}")
        return {
            "ready": False,
            "n_reads": dna["n"],
            "reason": "No grounded idea this time — read another reel and this refreshes.",
        }

    cited = list(dict.fromkeys(_VID_RE.findall(json.dumps(idea))))
    row = CreatorIdea(
        id="cdi_" + uuid.uuid4().hex[:12],
        user_id=user_id,
        cache_key=dna["cache_key"],
        niche=dna.get("niche"),
        format=idea.get("format"),
        gap_dimension=dna["gap_key"],
        idea=idea,
        source_video_ids=cited,
    )
    with session_scope() as s:
        s.add(row)
    return _envelope(row, dna, digest)
