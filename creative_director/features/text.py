"""Title + description feature extraction."""
from __future__ import annotations

import re
from typing import Optional

from loguru import logger


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "]"
)
_HASHTAG_RE = re.compile(r"#\w+")
_NUMBER_RE = re.compile(r"\d")
_WORD_RE = re.compile(r"\w+")

_text_model = None


def _load_text_model():
    global _text_model
    if _text_model is None:
        from sentence_transformers import SentenceTransformer

        _text_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _text_model


def _embed(text: str) -> Optional[list[float]]:
    try:
        model = _load_text_model()
        vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec.tolist()
    except Exception as e:
        logger.warning(f"Text embedding failed: {e}")
        return None


def all_caps_ratio(s: str) -> float:
    words = _WORD_RE.findall(s)
    if not words:
        return 0.0
    return sum(1 for w in words if len(w) >= 2 and w.isupper()) / len(words)


def extract_title_features(title: str) -> dict:
    title = title or ""
    return {
        "title_char_count": len(title),
        "title_word_count": len(_WORD_RE.findall(title)),
        "title_emoji_count": len(_EMOJI_RE.findall(title)),
        "title_question_mark": "?" in title,
        "title_has_number": bool(_NUMBER_RE.search(title)),
        "title_all_caps_ratio": all_caps_ratio(title),
        "title_embedding": _embed(title) if title else None,
    }


def extract_description_features(description: str) -> dict:
    description = description or ""
    return {
        "description_char_count": len(description),
        "hashtag_count": len(_HASHTAG_RE.findall(description)),
    }
