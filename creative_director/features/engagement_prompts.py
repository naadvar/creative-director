"""Detect engagement-driving phrasings in a reel's title/caption/hook.

These are the mechanical viral mechanics: comment-bait, save-prompts, tag
prompts, follow-prompts. They drive the engagement counts that the IG
algorithm reads as a quality signal, so reels that contain them tend to
travel further than reels that don't (with everything else equal).

Pure function: takes raw text fields, returns a dict of features. No DB
access. Use ``extract_for_features`` to get a dict keyed to the column
names on ``VideoFeatures``.
"""
from __future__ import annotations

import re
from typing import Optional


# Patterns are intentionally generous (case-insensitive substring/regex). False
# positives are tolerable for a binary signal; missed matches are not.
_SAVE_PATTERNS = re.compile(
    r"\b(save (this|for later|to|it)|save your spot|don'?t forget to save|saved for later)\b",
    re.IGNORECASE,
)
_TAG_PATTERNS = re.compile(
    r"\b(tag (a|your|someone|that|a friend|a buddy|the)|tag (\w+ )?(below|who)|@mention)\b",
    re.IGNORECASE,
)
_FOLLOW_PATTERNS = re.compile(
    r"\b(follow (for more|me for|along|@\w+)|follow for daily|hit the follow)\b",
    re.IGNORECASE,
)
_COMMENT_PATTERNS = re.compile(
    r"\b(comment (\"|')[^\"']{1,30}(\"|')|"
    r"comment (\w+ )?(below|down below|if|your|the)|"
    r"let me know (in the comments|below)|"
    r"tell me (in the comments|below)|"
    r"drop a (comment|note)|"
    r"comments? section|"
    r"reply (in the )?comments?)\b",
    re.IGNORECASE,
)
_QUESTION_PATTERNS = re.compile(
    r"^\s*(do you|did you|are you|can you|have you|what(\\'?s)?|why|how|where|when|who)\b",
    re.IGNORECASE,
)


def _text_or_empty(s: Optional[str]) -> str:
    return s or ""


def detect_engagement(
    *,
    title: Optional[str],
    description: Optional[str],
    transcript: Optional[str],
    transcript_first_3s: Optional[str],
) -> dict:
    """Scan the reel's text surfaces for engagement-driving phrasings.

    Title + description carry the explicit prompt (creators put "save this!"
    in the caption). Full transcript catches spoken prompts at the END of
    the reel ("comment if you tried this"). The first-3s transcript catches
    HOOK prompts ("comment your favorite exercise" as an opener).
    """
    title_text = _text_or_empty(title)
    desc_text = _text_or_empty(description)
    transcript_text = _text_or_empty(transcript)
    hook_text = _text_or_empty(transcript_first_3s)

    # Combine the "caption" surfaces (title + description) and the "spoken"
    # surfaces (transcript) -- they're slightly different idioms.
    caption_blob = f"{title_text}\n{desc_text}"
    spoken_blob = transcript_text

    has_save = bool(
        _SAVE_PATTERNS.search(caption_blob) or _SAVE_PATTERNS.search(spoken_blob)
    )
    has_tag = bool(
        _TAG_PATTERNS.search(caption_blob) or _TAG_PATTERNS.search(spoken_blob)
    )
    has_follow = bool(
        _FOLLOW_PATTERNS.search(caption_blob) or _FOLLOW_PATTERNS.search(spoken_blob)
    )
    has_comment = bool(
        _COMMENT_PATTERNS.search(caption_blob) or _COMMENT_PATTERNS.search(spoken_blob)
    )

    # Hook question heuristic: title starts with a question word, OR the
    # first-3s transcript starts with one. Marks the "did you know..." /
    # "have you ever..." opener that prompts the viewer's brain to answer.
    has_question_hook = bool(
        _QUESTION_PATTERNS.match(title_text)
        or _QUESTION_PATTERNS.match(hook_text)
        or (hook_text.endswith("?") and len(hook_text.split()) <= 12)
    )

    return {
        "has_save_prompt": has_save,
        "has_tag_prompt": has_tag,
        "has_follow_prompt": has_follow,
        "has_comment_prompt": has_comment,
        "has_question_hook": has_question_hook,
        "prompt_count": int(has_save)
        + int(has_tag)
        + int(has_follow)
        + int(has_comment)
        + int(has_question_hook),
    }


def extract_for_features(
    *,
    title: Optional[str],
    description: Optional[str],
    transcript: Optional[str],
    transcript_first_3s: Optional[str],
) -> dict:
    """Return a dict keyed to ``VideoFeatures`` column names."""
    d = detect_engagement(
        title=title,
        description=description,
        transcript=transcript,
        transcript_first_3s=transcript_first_3s,
    )
    return {
        "engagement_has_save_prompt": int(d["has_save_prompt"]),
        "engagement_has_tag_prompt": int(d["has_tag_prompt"]),
        "engagement_has_follow_prompt": int(d["has_follow_prompt"]),
        "engagement_has_comment_prompt": int(d["has_comment_prompt"]),
        "engagement_has_question_hook": int(d["has_question_hook"]),
        "engagement_prompt_count": d["prompt_count"],
    }
