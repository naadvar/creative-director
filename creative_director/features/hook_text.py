"""Hook-text features: what the first 3 seconds of a reel actually SAY.

Up to now the model only sees ``transcript_word_count`` -- whether the
creator talks at all and how much. The *words* themselves are an enormous
missed signal: hook quality is largely about what's said in the first
~3 seconds (the swipe-or-stay window).

We add two layers:
  1. A sentence embedding of the hook text (SentenceTransformer 384d),
     plus a per-niche/tier "winner centroid" similarity computed at model-
     dataset build time (analogous to ``thumb_sim_winner`` / ``title_sim_winner``).
  2. A small set of human-interpretable flags: starts-with-a-question,
     uses second-person 'you', uses a number, includes negation
     ('stop', 'never', "you're not"). These are SHAP-readable and feed
     into the same dashboard advice surface.

Demo reels (transcript_first_3s empty) get NaN/zero flags -- handled by
LightGBM's missing-value support so they don't poison the regression.
"""
from __future__ import annotations

import re
from typing import Optional


# Question-opener words at the start of the hook.
_Q_START = re.compile(
    r"^\s*(do|did|does|are|am|is|was|were|can|could|should|would|will|"
    r"have|has|had|what|why|how|where|when|who|which|whose)\b",
    re.IGNORECASE,
)
# Second-person markers (you / your / yourself / you're / you've).
_YOU = re.compile(r"\byou\b|\byour\b|\byou'?re\b|\byou'?ve\b|\byourself\b", re.IGNORECASE)
# Digits OR number words.
_NUM = re.compile(
    r"\b\d+\b|\b(one|two|three|four|five|six|seven|eight|nine|ten|"
    r"twenty|thirty|fifty|hundred|thousand)\b",
    re.IGNORECASE,
)
# Common negation / contrarian opener vocabulary.
_NEG = re.compile(
    r"\b(stop|never|don'?t|do not|aren'?t|isn'?t|can'?t|won'?t|"
    r"shouldn'?t|wouldn'?t|wrong|mistake|bad|worst|nobody|nothing)\b",
    re.IGNORECASE,
)


def extract_flags(transcript_first_3s: Optional[str]) -> dict:
    """Compute per-row interpretable hook flags. Does NOT compute embedding
    (that needs the SentenceTransformer model -- see ``embed_hook_text``).
    """
    text = (transcript_first_3s or "").strip()
    has_text = bool(text)
    if not has_text:
        return {
            "hook_starts_with_question": 0,
            "hook_uses_you": 0,
            "hook_uses_number": 0,
            "hook_has_negation": 0,
            "hook_word_count": 0,
        }
    return {
        "hook_starts_with_question": int(bool(_Q_START.match(text))),
        "hook_uses_you": int(bool(_YOU.search(text))),
        "hook_uses_number": int(bool(_NUM.search(text))),
        "hook_has_negation": int(bool(_NEG.search(text))),
        "hook_word_count": len(text.split()),
    }


def load_embedder():
    """Lazy-load the SentenceTransformer. Same model used for title_embedding
    elsewhere in the pipeline -- 384-dim all-MiniLM-L6-v2.

    CRITICAL: force device="cpu". This machine's RTX 2060 is thermally
    damaged (see project memory); torch.cuda.is_available() returns True but
    running transformer matmuls on it crashes the box with a dxgkrnl GPU
    driver fault. Never let SentenceTransformer auto-select CUDA here.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2", device="cpu"
    )


def embed_hook_text(model, transcript_first_3s: Optional[str]) -> Optional[list[float]]:
    """Encode the hook text with a preloaded SentenceTransformer.

    Returns a Python list of floats (JSON-serializable) or None for empty
    hooks (silent demos). Callers should batch this when possible -- one
    embed at a time is slow because of model overhead per call.
    """
    text = (transcript_first_3s or "").strip()
    if not text:
        return None
    vec = model.encode([text], convert_to_numpy=True, show_progress_bar=False)[0]
    return [float(x) for x in vec]


def batch_embed(model, texts: list[Optional[str]]) -> list[Optional[list[float]]]:
    """Vectorised batch encode -- 30-50x faster than per-row for many rows."""
    nonempty_indices: list[int] = []
    nonempty_texts: list[str] = []
    for i, t in enumerate(texts):
        s = (t or "").strip()
        if s:
            nonempty_indices.append(i)
            nonempty_texts.append(s)

    if not nonempty_texts:
        return [None] * len(texts)

    vecs = model.encode(
        nonempty_texts,
        batch_size=128,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    out: list[Optional[list[float]]] = [None] * len(texts)
    for j, idx in enumerate(nonempty_indices):
        out[idx] = [float(x) for x in vecs[j]]
    return out
