"""Prompt builders for caption + hashtag generation."""

from __future__ import annotations

from agent.sources.profile import SourceContent

VOICE_GUIDELINES = """\
Voice for Anuj Bansal's LinkedIn (engagement-first, emoji-rich):

- First person, confident, conversational, a little playful.
- Hook: at most 2 short lines, visible above LinkedIn's "...more" fold.
  Lead with a specific claim, a concrete number, a contrarian take, or a
  pointed question. Open with a single hook emoji when natural
  (e.g. 👇, 🚨, 🧠, 📊, 💡, 🔥, ⚡, 🎯). The hook must read fine on its own.
- Whitespace: one blank line every 1-2 sentences. No long paragraphs.
  The post must scan on mobile in under 5 seconds.
- Emoji bullets: mark list items, scene beats, or framework steps with
  emoji markers (▶️, ✅, ❌, 🔹, 📌, 🎯, 1️⃣ 2️⃣ 3️⃣) so the structure
  is visible at a glance. Pick markers that fit the meaning, never
  decorative spam.
- Metric-heavy: cite specific numbers when the source provides them.
  Never invent metrics. Make metrics pop with an arrow or marker
  (e.g. "→ 38% fewer false positives", "▶️ 95% accuracy").
- Technical but accessible: explain the "what" briefly, then "why it
  matters". General readers should grasp the takeaway even if the
  underlying tech is unfamiliar. Translate jargon into plain language.
- Target audience: hiring managers and peers in Business Analyst /
  Data Analyst / Data Scientist roles in the US.
- Tone: thoughtful, grounded in real work, warm. Avoid hype words
  ("revolutionary", "10x", "blown away"). Emojis are encouraged for
  pacing and warmth: aim for 4 to 7 emojis spread across the post
  (hook, section markers, key metric, takeaway, CTA). Never emoji
  walls or 3+ emojis in a row.
- Closer: end with a clear engagement CTA - a direct question, a
  "what would you add?" prompt, or a "save this if useful" nudge.
  Invite the reader's own experience. Never spammy "agree? repost!".
- Length: 700 to 1300 characters total (inclusive).
- Do NOT include hashtags inline; they are appended after the caption.
- Do NOT include URLs in the caption body.
- Do NOT mention past employer names (e.g. Scaler Academy, Unacademy,
  Vedantu) or past job titles from previous employment. Frame any
  work-experience lesson generically ("in a prior analytics role")."""


_TYPE_INSTRUCTIONS = {
    "project": (
        "Open with a punchy outcome (a metric or a decision the project "
        "enabled) plus a single hook emoji. Then walk through 3-4 "
        "emoji-bulleted beats: the problem, what you built, the one "
        "technical choice that mattered, the result. Translate any "
        "jargon so a non-technical reader gets the takeaway. Close with "
        "a question that invites discussion."
    ),
    "concept": (
        "Pick ONE concept from the supplied skill area. Open with a "
        "relatable hook (an analogy, a surprising claim, or a question). "
        "Explain the concept in plain language with a tiny concrete "
        "example. Use 2-4 emoji bullets to break the idea into bite-sized "
        "pieces a non-technical reader can follow. End by asking how "
        "others apply it."
    ),
    "career": (
        "Open with a vivid scene or milestone plus a hook emoji. Then "
        "3-4 emoji-marked beats: what changed, what you learned, what "
        "surprised you, what it points toward. Do NOT name past "
        "employers. End with a question that invites the reader to "
        "share their own pivot or milestone."
    ),
}


_FORMAT_GUIDE = """\
Pick the engagement format best matching this topic from:
- hot-take: a contrarian opinion + 2-3 reasons + invite pushback.
  Use 🔥, 🚨, or 💭 in the hook to mark stance.
- story: a short scene from real work, 3-5 beats, ending in a lesson.
  Mark beats with ▶️ or ➡️ so the arc scans on mobile.
- list: 3-5 punchy items, each one short line, framed as mistakes,
  rules, or signals. Mark items with ✅/❌, 🔹, 📌, or 1️⃣ 2️⃣ 3️⃣.
- framework: a reusable mental model (2-4 steps or questions) the
  reader can copy. Mark steps with 1️⃣ 2️⃣ 3️⃣ or 🎯.

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
    """Return messages to generate 8-12 hashtags as a JSON array of strings."""
    user = (
        "Pick 8 to 12 LinkedIn hashtags for the post below to maximize "
        "reach across both broad and niche audiences.\n"
        "Mix:\n"
        "- 3-4 broad evergreen tags (e.g. #DataScience, #MachineLearning, "
        "#Analytics, #AI, #Tech) for wide discovery.\n"
        "- 4-6 niche/topic-specific tags tied to the caption content "
        "and the keywords list.\n"
        "- 1-2 community/role tags that hiring managers and peers "
        "follow (e.g. #DataAnalyst, #BusinessAnalyst, #DataScientist, "
        "#DataScienceCommunity, #CareerGrowth).\n"
        "Rules:\n"
        "- No spaces, no punctuation other than the leading #.\n"
        "- CamelCase multi-word tags (e.g. #AttentionUNet).\n"
        "- Avoid banned/spammy tags (#follow, #like, #viral, "
        "#followforfollow).\n"
        "- No duplicates.\n\n"
        f"Post type: {post_type}\n"
        f"Caption:\n{caption}\n\n"
        f"Keywords (use these to inspire niche tags): {', '.join(keywords)}\n\n"
        'Return ONLY a JSON array of strings, no prose. Example: '
        '["#DataScience", "#SHAP", "#MachineLearning"]'
    )
    return [{"role": "user", "content": user}]
