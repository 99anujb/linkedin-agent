"""Prompt builders for caption + hashtag generation."""

from __future__ import annotations

from agent.sources.profile import SourceContent

VOICE_GUIDELINES = """\
Voice for Anuj Bansal's LinkedIn:
- First person, confident but not boastful.
- Metric-heavy: cite specific numbers when the source provides them ($ amounts,
  %, throughput, accuracy). Never invent metrics.
- Technical but accessible: explain the "what" briefly, then "why it matters".
- Target audience: hiring managers and peers in Business Analyst / Data Analyst
  / Data Scientist roles in the US.
- Tone: thoughtful, grounded in real work. Avoid hype words ("revolutionary",
  "10x", "blown away"). Avoid emoji walls. One or two emoji at most, only if
  natural.
- Structure: hook (1 line) -> body (3-5 short paragraphs, blank lines between)
  -> soft CTA (1 line, a question or invite).
- Length: 800-1300 characters total.
- Do NOT include tags inline; they are appended separately after the caption.
- Do NOT include URLs in the caption body."""


_TYPE_INSTRUCTIONS = {
    "project": (
        "Write a project breakdown post. Lead with the outcome (a metric or "
        "decision the project enabled). Then walk briefly through what you "
        "built, one technical choice that mattered, and what you learned. "
        "End with a question that invites discussion."
    ),
    "concept": (
        "Write a concept explainer post. Pick ONE concept from the supplied "
        "skill category and explain it in plain language with a tiny concrete "
        "example. End by asking how others apply it."
    ),
    "tip": (
        "Write a tip/insight post. Share ONE concrete lesson from the supplied "
        "experience bullets. State the situation, the move, the outcome (with "
        "metric). End with a one-line takeaway and a question."
    ),
}


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
            "\nMetrics from the source (use these exact numbers if you cite any):\n"
            + "\n".join(f"- {k}: {v}" for k, v in source.metrics.items())
        )
    user = (
        f"Post type: {post_type}\n"
        f"Source title: {source.title}\n"
        f"Source content:\n{source.body}\n"
        f"Role targets: {', '.join(role_targets)}\n"
        f"{metrics_block}\n\n"
        f"Instructions:\n{instructions}\n\n"
        "Return ONLY the caption text. No preamble, no quotes, no hashtags."
    )
    return [
        {"role": "user", "content": VOICE_GUIDELINES + "\n\n" + user},
    ]


def build_hashtag_messages(
    post_type: str,
    caption: str,
    keywords: list[str],
) -> list[dict[str, str]]:
    """Return messages to generate 5-8 hashtags as a JSON array of strings."""
    user = (
        "Pick 5 to 8 LinkedIn hashtags for the post below.\n"
        "Rules:\n"
        "- Mix evergreen tags (e.g. #DataScience, #MachineLearning) with niche tags "
        "specific to the content.\n"
        "- No spaces, no punctuation other than the leading #.\n"
        "- CamelCase multi-word tags (e.g. #AttentionUNet).\n"
        "- Avoid banned/spammy tags (#follow, #like, #viral).\n\n"
        f"Post type: {post_type}\n"
        f"Caption:\n{caption}\n\n"
        f"Keywords (use these to inspire niche tags): {', '.join(keywords)}\n\n"
        'Return ONLY a JSON array of strings, no prose. Example: ["#DataScience", "#SHAP"]'
    )
    return [{"role": "user", "content": user}]
