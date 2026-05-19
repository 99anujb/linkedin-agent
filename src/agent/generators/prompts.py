"""Prompt builders for caption + hashtag generation."""

from __future__ import annotations

from agent.sources.profile import SourceContent

VOICE_GUIDELINES = """\
Voice for Anuj Bansal's LinkedIn:

- First person, confident but not boastful.
- Hook: at most 2 short lines, visible above LinkedIn's "...more" fold.
  Lead with a specific claim, a concrete number, or a contrarian take.
  The hook must read fine on its own.
- Whitespace: one blank line every 1-2 sentences. No long paragraphs.
- Metric-heavy: cite specific numbers when the source provides them.
  Never invent metrics.
- Technical but accessible: explain the "what" briefly, then "why it
  matters".
- Target audience: hiring managers and peers in Business Analyst /
  Data Analyst / Data Scientist roles in the US.
- Tone: thoughtful, grounded in real work. Avoid hype words
  ("revolutionary", "10x", "blown away"). Avoid emoji walls. Up to two
  emoji total, only when natural.
- Closer: end with a question that invites the reader's own experience.
  A soft repost prompt is allowed only when it fits the format; never
  spammy "agree? repost!".
- Length: 700 to 1300 characters total (inclusive).
- Do NOT include hashtags inline; they are appended after the caption.
- Do NOT include URLs in the caption body.
- Do NOT mention past employer names (e.g. Scaler Academy, Unacademy,
  Vedantu) or past job titles from previous employment. Frame any
  work-experience lesson generically ("in a prior analytics role")."""


_TYPE_INSTRUCTIONS = {
    "project": (
        "Lead with the outcome (a metric or a decision the project "
        "enabled). Then walk through what you built, one technical "
        "choice that mattered, and what you learned. End with a "
        "question that invites discussion."
    ),
    "concept": (
        "Pick ONE concept from the supplied skill area and explain it "
        "in plain language with a tiny concrete example. End by asking "
        "how others apply it."
    ),
    "career": (
        "Lead with the milestone or a vivid scene from the journey. "
        "Explain what it meant, what you learned, and what it points "
        "toward. Do NOT name past employers. End with a question that "
        "invites the reader to share their own pivot or milestone."
    ),
}


_FORMAT_GUIDE = """\
Pick the engagement format best matching this topic from:
- hot-take: a contrarian opinion + 2-3 reasons + invite pushback.
- story: a short scene from real work, 3-5 beats, ending in a lesson.
- list: 3-5 punchy items, each one short line, framed as mistakes,
  rules, or signals.
- framework: a reusable mental model (2-4 steps or questions) the
  reader can copy.

Output format (exactly):
FORMAT: <chosen-format>
CAPTION:
<caption text following the voice guidelines and the chosen format>"""


def build_caption_messages(
    post_type: str,
    source: SourceContent,
    role_targets: list[str],
) -> list[dict[str, str]]:
    """Return messages for Anthropic Messages API to generate the caption."""
    instructions = _TYPE_INSTRUCTIONS[post_type]
    metrics_block = ""
    if source.metrics:
        metrics_block = (
            "\nMetrics from the source (use these exact numbers if you "
            "cite any):\n" + "\n".join(f"- {k}: {v}" for k, v in source.metrics.items())
        )
    user = (
        f"Post type: {post_type}\n"
        f"Source title: {source.title}\n"
        f"Source content:\n{source.body}\n"
        f"Role targets: {', '.join(role_targets)}\n"
        f"{metrics_block}\n\n"
        f"Type-specific instructions:\n{instructions}\n\n"
        f"{_FORMAT_GUIDE}"
    )
    return [
        {"role": "user", "content": VOICE_GUIDELINES + "\n\n" + user},
    ]


def parse_format_choice(raw: str) -> tuple[str, str]:
    """Split a `FORMAT: x\\nCAPTION:\\n...` response into (format, caption)."""
    default_format = "framework"
    raw = raw.strip()
    if not raw.startswith("FORMAT:"):
        return default_format, raw
    head, _, tail = raw.partition("\nCAPTION:")
    fmt = head.removeprefix("FORMAT:").strip().lower()
    if fmt not in {"hot-take", "story", "list", "framework"}:
        fmt = default_format
    caption = tail.strip() if tail else raw
    return fmt, caption


def build_hashtag_messages(
    post_type: str,
    caption: str,
    keywords: list[str],
) -> list[dict[str, str]]:
    """Return messages to generate 5-8 hashtags as a JSON array of strings."""
    user = (
        "Pick 5 to 8 LinkedIn hashtags for the post below.\n"
        "Rules:\n"
        "- Mix evergreen tags (e.g. #DataScience, #MachineLearning) with "
        "niche tags specific to the content.\n"
        "- No spaces, no punctuation other than the leading #.\n"
        "- CamelCase multi-word tags (e.g. #AttentionUNet).\n"
        "- Avoid banned/spammy tags (#follow, #like, #viral).\n\n"
        f"Post type: {post_type}\n"
        f"Caption:\n{caption}\n\n"
        f"Keywords (use these to inspire niche tags): {', '.join(keywords)}\n\n"
        'Return ONLY a JSON array of strings, no prose. Example: '
        '["#DataScience", "#SHAP"]'
    )
    return [{"role": "user", "content": user}]
