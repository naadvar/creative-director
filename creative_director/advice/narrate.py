"""LLM narration layer — turns structured breakdowns into creative-director prose.

Takes the structured aggregate + frame breakdowns for a video and asks Claude
to write them up as a concise, human-readable creative-director note. The model
is given hard constraints so it cannot overclaim:
  - phrase findings as correlations ("winners tend to..."), never causal commands
  - present likely-proxy features (hashtags) as weak signals, not levers
  - lead with what matters, stay honest about confidence
"""
from __future__ import annotations

from creative_director.advice.breakdown import VideoBreakdown, format_breakdown
from creative_director.advice.timeline_benchmark import (
    FrameBreakdown,
    format_frame_breakdown,
)
from creative_director.config import settings


_NARRATOR_SYSTEM = """You are a creative director for YouTube Shorts creators. \
You receive a structured analysis of one fitness Short — how it compares to \
high-performing videos of the same content archetype — and write it up as a \
short, sharp coaching note the creator can act on.

Hard rules:
- The data is CORRELATIONAL. It describes what high-performing videos tend to \
look like; it does NOT prove cause. Phrase findings as comparisons ("winners \
in your niche tend to open with a face by the first second") — never as \
guaranteed-outcome commands ("do this and you'll go viral").
- Any finding tagged as a likely proxy (e.g. hashtag counts) must be presented \
as a weak signal, not a lever. Say so plainly.
- Lead with the 1-2 findings that matter most. Do not list every finding with \
equal weight.
- If the video already matches winners on a dimension, say so briefly — do not \
invent problems.
- Be specific and concrete (cite the actual numbers), but concise: ~150-220 words.
- End with one honest sentence on confidence: this is pattern-matching against \
a small sample, not a guarantee.
- No emojis. No hype. Write like an experienced editor giving a peer real notes."""


class NarrationError(RuntimeError):
    pass


def narrate_breakdown(
    video_breakdown: VideoBreakdown,
    frame_breakdown: FrameBreakdown,
) -> str:
    """Render a video's structured breakdowns into creative-director prose."""
    import anthropic

    api_key = settings.anthropic_api_key
    if not api_key:
        raise NarrationError(
            "No Anthropic API key. Set ANTHROPIC_API_KEY in .env "
            "(get one at console.anthropic.com)."
        )

    client = anthropic.Anthropic(api_key=api_key)

    structured = (
        format_breakdown(video_breakdown)
        + "\n\n"
        + format_frame_breakdown(frame_breakdown)
    )

    try:
        response = client.messages.create(
            model=settings.narrator_model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=_NARRATOR_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Here is the structured analysis of one fitness Short. "
                        "Write the creative-director note.\n\n" + structured
                    ),
                }
            ],
        )
    except anthropic.APIError as e:
        raise NarrationError(f"Anthropic API call failed: {e}") from e

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise NarrationError("Model returned no text content.")
    return text
