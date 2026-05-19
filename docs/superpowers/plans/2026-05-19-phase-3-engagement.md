# Phase 3 Engagement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current essay-style caption and generic Unsplash photo with a Claude-picked engagement format and a topic-relevant generated PNG, hosted from the repo via `raw.githubusercontent.com`.

**Architecture:** Caption prompt picks one of `{hot-take, story, list, framework}` per topic and writes in a hook-first / whitespace-heavy style. After caption generation, an image picker renders either a Pygments code card (project / concept) or a Pillow quote card (career), saves the PNG under `db/images/<draft_id>.png`, and pushes it to `main` from inside the agent so the raw URL is live before the preview email is sent.

**Tech Stack:** Pillow, Pygments (new), existing Anthropic Messages API, GitPython-free git via `subprocess`, existing pytest + respx test stack.

**Spec:** `docs/superpowers/specs/2026-05-19-phase3-engagement-design.md`

---

## File structure

**New:**
- `src/agent/generators/snippet.py` — Claude call → `(snippet_text, language)`
- `src/agent/generators/image_card.py` — `render_code_card`, `render_quote_card`, `pick_and_render`
- `src/agent/delivery/git_publish.py` — `commit_and_push(paths, message)`
- `assets/fonts/Inter-Regular.ttf`, `assets/fonts/Inter-Bold.ttf` — bundled fonts
- `scripts/preview_card.py` — local renderer for visual eyeballing
- `db/images/.gitkeep` — ensures the directory is tracked
- `tests/unit/test_snippet.py`
- `tests/unit/test_image_card.py`
- `tests/unit/test_git_publish.py`
- `tests/unit/test_prompts.py`

**Modified:**
- `src/agent/generators/prompts.py` — new voice guidelines + format picker
- `src/agent/draft.py` — wire snippet/image_card/git_publish into the pipeline
- `src/agent/config.py` — add `github_raw_base`
- `tests/unit/test_draft_pipeline.py` — extend happy-path assertions for new image URL
- `requirements.txt` — add `Pillow`, `Pygments`

---

## Task 1: Add dependencies, font assets, and image directory

**Files:**
- Modify: `requirements.txt`
- Create: `assets/fonts/Inter-Regular.ttf`
- Create: `assets/fonts/Inter-Bold.ttf`
- Create: `db/images/.gitkeep`

- [ ] **Step 1: Add Pillow and Pygments to requirements.txt**

Append to `requirements.txt`:

```
Pillow>=10.4
Pygments>=2.18
```

- [ ] **Step 2: Install the new deps locally**

```bash
pip install -r requirements.txt
```

Expected: both packages install without conflicts.

- [ ] **Step 3: Bundle Inter Regular + Bold fonts**

Download from `https://rsms.me/inter/font-files/Inter-Regular.ttf` and `https://rsms.me/inter/font-files/Inter-Bold.ttf`. Save to `assets/fonts/`.

```bash
mkdir -p assets/fonts
curl -L -o assets/fonts/Inter-Regular.ttf https://rsms.me/inter/font-files/Inter-Regular.ttf
curl -L -o assets/fonts/Inter-Bold.ttf    https://rsms.me/inter/font-files/Inter-Bold.ttf
```

Expected: two `.ttf` files, each ~300-500 KB.

- [ ] **Step 4: Ensure `db/images/` is committed and empty**

```bash
mkdir -p db/images
touch db/images/.gitkeep
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt assets/fonts/Inter-Regular.ttf assets/fonts/Inter-Bold.ttf db/images/.gitkeep
git commit -m "chore(deps): add Pillow + Pygments and bundle Inter fonts"
```

---

## Task 2: Rewrite voice guidelines + add format picker

**Files:**
- Test: `tests/unit/test_prompts.py` (new)
- Modify: `src/agent/generators/prompts.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_prompts.py`:

```python
from __future__ import annotations

from agent.generators.prompts import (
    VOICE_GUIDELINES,
    build_caption_messages,
    parse_format_choice,
)
from agent.sources.profile import SourceContent


def _source() -> SourceContent:
    return SourceContent(
        source_ref="proj:fraud",
        title="Fraud detection model",
        body="Built an XGBoost classifier that reduced false positives by 38%.",
        keywords=["fraud", "xgboost", "ml"],
        metrics={"false_positive_reduction": "38%"},
    )


def test_voice_guidelines_enforces_engagement_rules() -> None:
    g = VOICE_GUIDELINES
    assert "Hook" in g
    assert "2 short lines" in g
    assert "700" in g and "1300" in g
    assert "blank line" in g.lower()
    assert "Avoid hype" in g or "avoid hype" in g.lower()


def test_build_caption_messages_includes_format_picker() -> None:
    msgs = build_caption_messages("project", _source(), ["Data Scientist"])
    content = msgs[0]["content"]
    assert "hot-take" in content
    assert "story" in content
    assert "list" in content
    assert "framework" in content
    assert "FORMAT:" in content
    assert "CAPTION:" in content


def test_parse_format_choice_extracts_picked_format_and_caption() -> None:
    raw = "FORMAT: list\nCAPTION:\nLine one.\n\nLine two.\n\nQ?"
    fmt, caption = parse_format_choice(raw)
    assert fmt == "list"
    assert caption.startswith("Line one.")
    assert "FORMAT:" not in caption


def test_parse_format_choice_falls_back_when_label_missing() -> None:
    raw = "Just a caption without labels.\n\nQ?"
    fmt, caption = parse_format_choice(raw)
    assert fmt == "framework"  # default
    assert caption == raw.strip()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_prompts.py -v
```

Expected: ImportError or AttributeError — `parse_format_choice` doesn't exist yet, new voice lines absent.

- [ ] **Step 3: Rewrite `src/agent/generators/prompts.py`**

Replace the file with:

```python
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
            "cite any):\n"
            + "\n".join(f"- {k}: {v}" for k, v in source.metrics.items())
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_prompts.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run the full suite to confirm no regressions**

```bash
pytest -q
```

Expected: same number of tests pass as before, plus the 4 new ones.

- [ ] **Step 6: Update `caption.py` to strip the format label**

Modify `src/agent/generators/caption.py` so the returned caption no longer leaks `FORMAT: ...` into the LinkedIn post. Add the call to `parse_format_choice` and return only the caption text:

```python
"""Generate a LinkedIn caption via Anthropic's Messages API."""

from __future__ import annotations

import logging
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from agent.generators.prompts import build_caption_messages, parse_format_choice
from agent.sources.profile import SourceContent

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

log = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    reraise=True,
)
def generate_caption(
    client: Any,
    *,
    post_type: str,
    source: SourceContent,
    role_targets: list[str],
    model: str = DEFAULT_MODEL,
) -> str:
    messages = build_caption_messages(post_type, source, role_targets)
    log.info("Generating caption (model=%s, post_type=%s)", model, post_type)
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=messages,
    )
    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()
    _fmt, caption = parse_format_choice(raw)
    return caption
```

- [ ] **Step 7: Re-run the suite**

```bash
pytest -q
```

Expected: same green count.

- [ ] **Step 8: Commit**

```bash
git add tests/unit/test_prompts.py src/agent/generators/prompts.py src/agent/generators/caption.py
git commit -m "feat(prompts): engagement voice + format picker"
```

---

## Task 3: Quote card renderer

**Files:**
- Test: `tests/unit/test_image_card.py` (new)
- Create: `src/agent/generators/image_card.py`

- [ ] **Step 1: Write a failing test for `render_quote_card`**

Create `tests/unit/test_image_card.py`:

```python
from __future__ import annotations

from io import BytesIO

from PIL import Image

from agent.generators.image_card import (
    CARD_HEIGHT,
    CARD_WIDTH,
    render_quote_card,
)


def _open(b: bytes) -> Image.Image:
    return Image.open(BytesIO(b))


def test_render_quote_card_returns_png_of_expected_size() -> None:
    png = render_quote_card("My hook line one.\nMy hook line two.")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    img = _open(png)
    assert img.size == (CARD_WIDTH, CARD_HEIGHT)
    assert img.format == "PNG"


def test_render_quote_card_handles_empty_text() -> None:
    png = render_quote_card("")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 2: Run the test, watch it fail**

```bash
pytest tests/unit/test_image_card.py -v
```

Expected: ImportError — module doesn't exist yet.

- [ ] **Step 3: Implement minimal `image_card.py`**

Create `src/agent/generators/image_card.py`:

```python
"""Pillow / Pygments image card renderers for LinkedIn posts."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

CARD_WIDTH = 1200
CARD_HEIGHT = 675

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FONT_DIR = _REPO_ROOT / "assets" / "fonts"
_FONT_REGULAR = _FONT_DIR / "Inter-Regular.ttf"
_FONT_BOLD = _FONT_DIR / "Inter-Bold.ttf"

_BG_TOP = (10, 20, 40)
_BG_BOTTOM = (32, 64, 128)
_TEXT_COLOR = (240, 240, 245)
_FOOTER_COLOR = (160, 175, 200)
_HANDLE = "@anuj-bansal"
_HOOK_FONT_SIZE = 56
_FOOTER_FONT_SIZE = 28
_SIDE_PADDING = 80


def _gradient_background(width: int, height: int) -> Image.Image:
    base = Image.new("RGB", (width, height), _BG_TOP)
    top_r, top_g, top_b = _BG_TOP
    bot_r, bot_g, bot_b = _BG_BOTTOM
    pixels = base.load()
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(top_r + (bot_r - top_r) * t)
        g = int(top_g + (bot_g - top_g) * t)
        b = int(top_b + (bot_b - top_b) * t)
        for x in range(width):
            pixels[x, y] = (r, g, b)
    return base


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not text.strip():
        return [""]
    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.getlength(candidate) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def render_quote_card(text: str) -> bytes:
    """Render the hook as a centered quote on a gradient background."""
    img = _gradient_background(CARD_WIDTH, CARD_HEIGHT)
    draw = ImageDraw.Draw(img)
    hook_font = ImageFont.truetype(str(_FONT_BOLD), _HOOK_FONT_SIZE)
    footer_font = ImageFont.truetype(str(_FONT_REGULAR), _FOOTER_FONT_SIZE)

    max_width = CARD_WIDTH - _SIDE_PADDING * 2
    lines = _wrap(text, hook_font, max_width)
    line_height = _HOOK_FONT_SIZE + 12
    total_text_height = line_height * len(lines)
    y = (CARD_HEIGHT - total_text_height) // 2

    for line in lines:
        line_width = hook_font.getlength(line)
        x = (CARD_WIDTH - line_width) // 2
        draw.text((x, y), line, font=hook_font, fill=_TEXT_COLOR)
        y += line_height

    footer_y = CARD_HEIGHT - _FOOTER_FONT_SIZE - 40
    footer_x = (CARD_WIDTH - footer_font.getlength(_HANDLE)) // 2
    draw.text((footer_x, footer_y), _HANDLE, font=footer_font, fill=_FOOTER_COLOR)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
```

- [ ] **Step 4: Run the test, watch it pass**

```bash
pytest tests/unit/test_image_card.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_image_card.py src/agent/generators/image_card.py
git commit -m "feat(image_card): quote card renderer"
```

---

## Task 4: Code snippet generator

**Files:**
- Test: `tests/unit/test_snippet.py` (new)
- Create: `src/agent/generators/snippet.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_snippet.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.generators.snippet import generate_snippet


def _mock_anthropic(text: str) -> MagicMock:
    block = type("B", (), {"type": "text", "text": text})()
    client = MagicMock()
    client.messages.create.return_value = MagicMock(content=[block])
    return client


def test_generate_snippet_parses_language_and_body() -> None:
    raw = "LANGUAGE: sql\nCODE:\nSELECT user_id, SUM(amount)\nFROM orders\nGROUP BY user_id;"
    client = _mock_anthropic(raw)
    snippet, language = generate_snippet(
        client, caption="window functions explainer", post_type="concept"
    )
    assert language == "sql"
    assert "SELECT" in snippet
    assert "LANGUAGE:" not in snippet
    assert "CODE:" not in snippet


def test_generate_snippet_defaults_language_when_missing() -> None:
    raw = "SELECT 1;"
    client = _mock_anthropic(raw)
    snippet, language = generate_snippet(
        client, caption="x", post_type="concept"
    )
    assert language == "text"
    assert snippet == "SELECT 1;"


def test_generate_snippet_empty_response_raises() -> None:
    client = _mock_anthropic("")
    with pytest.raises(ValueError):
        generate_snippet(client, caption="x", post_type="concept")
```

- [ ] **Step 2: Run tests, watch them fail**

```bash
pytest tests/unit/test_snippet.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `src/agent/generators/snippet.py`**

```python
"""Generate a tiny code / SQL / data snippet illustrating the caption."""

from __future__ import annotations

import logging
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 512

log = logging.getLogger(__name__)

_PROMPT = """\
Given the LinkedIn caption below, output a tiny illustrative code or data
snippet (at most 15 lines) that supports the caption's technical claim.
Pick whichever language matches: sql, python, json, yaml, bash, text.

Output format (exactly):
LANGUAGE: <one of: sql | python | json | yaml | bash | text>
CODE:
<the snippet, no markdown fences>

If no code helps the caption, output:
LANGUAGE: text
CODE:
<a 1-3 line plain-text illustration instead>

Post type: {post_type}
Caption:
{caption}"""


def _build_messages(*, caption: str, post_type: str) -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": _PROMPT.format(post_type=post_type, caption=caption),
        }
    ]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    reraise=True,
)
def generate_snippet(
    client: Any,
    *,
    caption: str,
    post_type: str,
    model: str = DEFAULT_MODEL,
) -> tuple[str, str]:
    """Return `(snippet_text, language)`. Raises ValueError on empty response."""
    log.info("Generating snippet (model=%s, post_type=%s)", model, post_type)
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=_build_messages(caption=caption, post_type=post_type),
    )
    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()
    if not raw:
        raise ValueError("snippet generator returned empty response")
    if not raw.startswith("LANGUAGE:"):
        return raw, "text"
    head, _, tail = raw.partition("\nCODE:")
    language = head.removeprefix("LANGUAGE:").strip().lower() or "text"
    snippet = tail.strip()
    if not snippet:
        return raw, "text"
    return snippet, language
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_snippet.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_snippet.py src/agent/generators/snippet.py
git commit -m "feat(snippet): Claude-generated code/data snippet for image cards"
```

---

## Task 5: Code card renderer

**Files:**
- Test: `tests/unit/test_image_card.py` (extend)
- Modify: `src/agent/generators/image_card.py`

- [ ] **Step 1: Add a failing test for `render_code_card`**

Append to `tests/unit/test_image_card.py`:

```python
def test_render_code_card_returns_png_of_expected_size() -> None:
    from agent.generators.image_card import render_code_card

    snippet = "SELECT id, SUM(amount)\nFROM orders\nGROUP BY id;"
    png = render_code_card(snippet, language="sql")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    img = _open(png)
    assert img.size == (CARD_WIDTH, CARD_HEIGHT)


def test_render_code_card_unknown_language_falls_back_to_text() -> None:
    from agent.generators.image_card import render_code_card

    png = render_code_card("hello world", language="klingon")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 2: Run tests, watch failure**

```bash
pytest tests/unit/test_image_card.py -v
```

Expected: ImportError on `render_code_card`.

- [ ] **Step 3: Implement `render_code_card`**

Append to `src/agent/generators/image_card.py`:

```python
from pygments import highlight
from pygments.formatters.img import ImageFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound


def _resize_to_card(img: Image.Image) -> Image.Image:
    """Center-paste the Pygments output onto a card-sized canvas."""
    canvas = _gradient_background(CARD_WIDTH, CARD_HEIGHT)
    snippet_max_w = CARD_WIDTH - _SIDE_PADDING * 2
    snippet_max_h = CARD_HEIGHT - _SIDE_PADDING * 2
    w, h = img.size
    scale = min(snippet_max_w / w, snippet_max_h / h, 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size
    x = (CARD_WIDTH - w) // 2
    y = (CARD_HEIGHT - h) // 2
    canvas.paste(img, (x, y))
    return canvas


def render_code_card(snippet: str, *, language: str) -> bytes:
    """Render the snippet as a syntax-highlighted code card."""
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except ClassNotFound:
        lexer = get_lexer_by_name("text", stripall=True)

    formatter = ImageFormatter(
        font_name=str(_FONT_REGULAR),
        font_size=22,
        line_numbers=False,
        style="monokai",
        image_pad=24,
        line_pad=6,
    )
    raw_png = highlight(snippet, lexer, formatter)
    snippet_img = Image.open(BytesIO(raw_png))
    card = _resize_to_card(snippet_img)

    buf = BytesIO()
    card.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_image_card.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_image_card.py src/agent/generators/image_card.py
git commit -m "feat(image_card): Pygments code card renderer"
```

---

## Task 6: Image picker

**Files:**
- Test: `tests/unit/test_image_card.py` (extend)
- Modify: `src/agent/generators/image_card.py`

- [ ] **Step 1: Add failing tests for `pick_and_render`**

Append to `tests/unit/test_image_card.py`:

```python
def test_pick_and_render_uses_code_card_for_project() -> None:
    from agent.generators.image_card import pick_and_render

    png = pick_and_render(
        post_type="project",
        hook="Reduced false positives by 38%.",
        snippet="SELECT id FROM orders;",
        language="sql",
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_pick_and_render_uses_quote_card_for_career() -> None:
    from agent.generators.image_card import pick_and_render

    png = pick_and_render(
        post_type="career",
        hook="Three years ago I doubted I belonged in data.",
        snippet=None,
        language=None,
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_pick_and_render_falls_back_to_quote_when_snippet_empty() -> None:
    from agent.generators.image_card import pick_and_render

    png = pick_and_render(
        post_type="project",
        hook="My hook.",
        snippet="",
        language="sql",
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 2: Run tests, watch failure**

```bash
pytest tests/unit/test_image_card.py -v
```

Expected: ImportError on `pick_and_render`.

- [ ] **Step 3: Implement `pick_and_render`**

Append to `src/agent/generators/image_card.py`:

```python
_CODE_TYPES = frozenset({"project", "concept"})


def pick_and_render(
    *,
    post_type: str,
    hook: str,
    snippet: str | None,
    language: str | None,
) -> bytes:
    """Pick code or quote card based on post_type, with quote-card fallback."""
    if post_type in _CODE_TYPES and snippet and language:
        try:
            return render_code_card(snippet, language=language)
        except Exception:  # noqa: BLE001 - fall back to quote on any render error
            log.warning("code card render failed; falling back to quote card")
    return render_quote_card(hook)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_image_card.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_image_card.py src/agent/generators/image_card.py
git commit -m "feat(image_card): pick code-or-quote card by post type"
```

---

## Task 7: `git_publish` helper

**Files:**
- Test: `tests/unit/test_git_publish.py` (new)
- Create: `src/agent/delivery/git_publish.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_git_publish.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.delivery.git_publish import commit_and_push


def test_commit_and_push_is_noop_when_ci_unset(monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    with patch("agent.delivery.git_publish.subprocess.run") as run:
        commit_and_push([Path("db/images/x.png")], message="m")
    run.assert_not_called()


def test_commit_and_push_runs_git_commands_when_ci_set(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    paths = [Path("db/images/a.png"), Path("db/images/b.png")]
    with patch("agent.delivery.git_publish.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        commit_and_push(paths, message="add cards")
    calls = [c.args[0] for c in run.call_args_list]
    assert calls[0] == [
        "git", "config", "user.name", "linkedin-agent",
    ]
    assert calls[1] == [
        "git", "config", "user.email", "noreply@anthropic.com",
    ]
    assert calls[2] == ["git", "add", "db/images/a.png", "db/images/b.png"]
    assert calls[3] == ["git", "commit", "-m", "add cards"]
    assert calls[4] == ["git", "push", "origin", "HEAD"]


def test_commit_and_push_swallows_nothing_to_commit(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    with patch("agent.delivery.git_publish.subprocess.run") as run:
        outputs = iter(
            [
                MagicMock(returncode=0),  # config name
                MagicMock(returncode=0),  # config email
                MagicMock(returncode=0),  # add
                MagicMock(returncode=1, stdout="nothing to commit", stderr=""),
            ]
        )
        run.side_effect = lambda *a, **kw: next(outputs)
        commit_and_push([Path("db/images/a.png")], message="m")
    # push is skipped when commit yielded nothing
    last_call = run.call_args_list[-1].args[0]
    assert last_call[1] == "commit"
```

- [ ] **Step 2: Run tests, watch failure**

```bash
pytest tests/unit/test_git_publish.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `git_publish.py`**

Create `src/agent/delivery/git_publish.py`:

```python
"""Stage, commit, and push artifact files from inside the agent."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path

log = logging.getLogger(__name__)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def commit_and_push(paths: Iterable[Path], *, message: str) -> None:
    """Commit and push the given files. No-op when CI env var is unset."""
    if not os.environ.get("CI"):
        log.info("commit_and_push: CI unset, skipping (paths=%s)", list(paths))
        return
    paths = [str(p) for p in paths]
    _run(["git", "config", "user.name", "linkedin-agent"])
    _run(["git", "config", "user.email", "noreply@anthropic.com"])
    _run(["git", "add", *paths])
    commit_res = _run(["git", "commit", "-m", message])
    if commit_res.returncode != 0:
        if "nothing to commit" in (commit_res.stdout + commit_res.stderr).lower():
            log.info("commit_and_push: nothing to commit")
            return
        log.warning(
            "commit_and_push: commit failed (rc=%s): %s",
            commit_res.returncode,
            commit_res.stderr,
        )
        return
    push_res = _run(["git", "push", "origin", "HEAD"])
    if push_res.returncode != 0:
        log.warning("commit_and_push: push failed: %s", push_res.stderr)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_git_publish.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_git_publish.py src/agent/delivery/git_publish.py
git commit -m "feat(git_publish): commit+push helper for in-agent artifact upload"
```

---

## Task 8: Add `github_raw_base` setting

**Files:**
- Test: `tests/unit/test_config.py` (extend if present, otherwise inline)
- Modify: `src/agent/config.py`

- [ ] **Step 1: Add a failing test**

Append to `tests/unit/test_config.py` (or create one):

```python
def test_settings_has_github_raw_base_default(monkeypatch, tmp_path):
    import os
    from agent.config import load_settings

    monkeypatch.setattr("agent.config.load_dotenv", lambda **_: None)
    env = {
        "ANTHROPIC_API_KEY": "x",
        "UNSPLASH_ACCESS_KEY": "x",
        "GMAIL_USERNAME": "a@b.com",
        "GMAIL_APP_PASSWORD": "x",
        "GMAIL_RECIPIENT": "a@b.com",
        "PROFILE_PATH": str(tmp_path / "p.json"),
        "DB_PATH": str(tmp_path / "db.sqlite"),
        "BUFFER_ACCESS_TOKEN": "x",
        "BUFFER_LINKEDIN_PROFILE_ID": "x",
        "HMAC_SECRET": "x" * 32,
        "APPROVAL_BASE_URL": "https://x.workers.dev",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = load_settings()
    assert s.github_raw_base == "https://raw.githubusercontent.com/99anujb/linkedin-agent/main"
```

- [ ] **Step 2: Run test, watch failure**

```bash
pytest tests/unit/test_config.py::test_settings_has_github_raw_base_default -v
```

Expected: AttributeError on `github_raw_base`.

- [ ] **Step 3: Add `github_raw_base` to `Settings` and `load_settings`**

Modify `src/agent/config.py`:

Inside `Settings`, after `post_local_time`:

```python
    github_raw_base: str = "https://raw.githubusercontent.com/99anujb/linkedin-agent/main"
```

Inside `load_settings`, before the closing `)`:

```python
        github_raw_base=os.environ.get(
            "GITHUB_RAW_BASE",
            "https://raw.githubusercontent.com/99anujb/linkedin-agent/main",
        ),
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_config.py -v
```

Expected: existing tests still green plus the new one.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_config.py src/agent/config.py
git commit -m "feat(config): add github_raw_base setting"
```

---

## Task 9: Wire image flow into `draft.py`

**Files:**
- Test: `tests/unit/test_draft_pipeline.py` (extend)
- Modify: `src/agent/draft.py`

- [ ] **Step 1: Extend the happy-path test for the new image flow**

Update `tests/unit/test_draft_pipeline.py` `_wire_fakes` and the happy-path test:

Replace `_wire_fakes` with:

```python
def _wire_fakes():
    anthropic = MagicMock()

    def _block(text: str):
        return type("B", (), {"type": "text", "text": text})()

    anthropic.messages.create.side_effect = [
        # caption (with FORMAT label)
        MagicMock(content=[_block("FORMAT: list\nCAPTION:\nHook.\n\nBody.\n\nQ?")]),
        # snippet
        MagicMock(content=[_block("LANGUAGE: sql\nCODE:\nSELECT 1;")]),
        # hashtags
        MagicMock(content=[_block('["#A","#B","#C","#D","#E"]')]),
    ]
    image_fn = MagicMock(return_value=ImageResult(url="http://img", credit="cred"))
    send_fn = MagicMock()
    return anthropic, image_fn, send_fn
```

Add at the bottom of `test_run_draft_happy_path`:

```python
    # New: image_url should point to the GitHub raw base, not Unsplash
    assert row["image_url"].startswith(
        "https://raw.githubusercontent.com/99anujb/linkedin-agent/main/db/images/"
    )
    assert row["image_url"].endswith(".png")
```

- [ ] **Step 2: Run the test, watch it fail**

```bash
pytest tests/unit/test_draft_pipeline.py::test_run_draft_happy_path -v
```

Expected: assertion failure — `image_url` still uses Unsplash URL.

- [ ] **Step 3: Wire snippet + image_card + git_publish into `draft.py`**

Replace the body of `run_draft` between caption generation and the `Draft(...)` call with:

```python
        caption = generate_caption(
            anthropic_client,
            post_type=decision.post_type,
            source=source,
            role_targets=profile.role_targets,
        )
        tags = generate_hashtags(
            anthropic_client,
            post_type=decision.post_type,
            caption=caption,
            keywords=source.keywords,
        )

        hook = "\n".join(caption.strip().splitlines()[:2])
        snippet_text: str | None = None
        snippet_language: str | None = None
        if decision.post_type in ("project", "concept"):
            try:
                snippet_text, snippet_language = generate_snippet(
                    anthropic_client,
                    caption=caption,
                    post_type=decision.post_type,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("snippet generation failed: %s", exc)

        draft_id = str(uuid.uuid4())
        image_path = Path("db/images") / f"{draft_id}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            png = pick_and_render(
                post_type=decision.post_type,
                hook=hook,
                snippet=snippet_text,
                language=snippet_language,
            )
            image_path.write_bytes(png)
            commit_and_push(
                [image_path],
                message=f"chore(image): card for draft {draft_id}",
            )
            raw_base = settings.github_raw_base.rstrip("/")
            image_url = f"{raw_base}/db/images/{draft_id}.png"
            image_credit = "Generated card"
        except Exception as exc:  # noqa: BLE001 - last-ditch fallback
            log.warning("card pipeline failed (%s); using Unsplash fallback", exc)
            fallback = image_fn(
                keywords=source.keywords, access_key=settings.unsplash_access_key
            )
            image_url = fallback.url
            image_credit = fallback.credit

        draft = Draft(
            id=draft_id,
            post_type=decision.post_type,
            source_ref=source.source_ref,
            caption=caption,
            hashtags=format_hashtags(tags),
            image_url=image_url,
            image_credit=image_credit,
        )
```

Add new imports at the top of `draft.py`:

```python
from pathlib import Path

from agent.delivery.git_publish import commit_and_push
from agent.generators.image_card import pick_and_render
from agent.generators.snippet import generate_snippet
```

- [ ] **Step 4: Run the test**

```bash
pytest tests/unit/test_draft_pipeline.py -v
```

Expected: all green. `image_fn` (Unsplash) is no longer the primary path.

- [ ] **Step 5: Add a fallback test**

Append to `tests/unit/test_draft_pipeline.py`:

```python
@freeze_time("2026-05-13T12:00:00Z")
def test_run_draft_falls_back_to_unsplash_on_render_failure(
    settings: Settings, monkeypatch,
) -> None:
    from agent.draft import run_draft as _run_draft

    monkeypatch.setattr(
        "agent.draft.pick_and_render", lambda **_: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    anthropic, image_fn, send_fn = _wire_fakes()
    result = _run_draft(
        settings,
        anthropic_client=anthropic,
        image_fn=image_fn,
        email_send_fn=send_fn,
        today=date(2026, 5, 13),
    )
    assert result.status == "drafted"
    image_fn.assert_called_once()
```

- [ ] **Step 6: Run all tests**

```bash
pytest -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_draft_pipeline.py src/agent/draft.py
git commit -m "feat(draft): wire snippet, image card, and git push into draft pipeline"
```

---

## Task 10: Preview script

**Files:**
- Create: `scripts/preview_card.py`

- [ ] **Step 1: Write the preview script**

Create `scripts/preview_card.py`:

```python
"""Render sample quote + code cards to tmp/ for visual eyeballing."""

from __future__ import annotations

from pathlib import Path

from agent.generators.image_card import render_code_card, render_quote_card

OUT = Path("tmp")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    (OUT / "preview_quote.png").write_bytes(
        render_quote_card(
            "Three years ago I shipped a model with no test coverage.\n"
            "It cost us a quarter."
        )
    )
    (OUT / "preview_code_sql.png").write_bytes(
        render_code_card(
            "WITH ranked AS (\n"
            "  SELECT id, score,\n"
            "         RANK() OVER (PARTITION BY region ORDER BY score DESC) AS r\n"
            "  FROM customers\n"
            ")\n"
            "SELECT * FROM ranked WHERE r <= 3;",
            language="sql",
        )
    )
    (OUT / "preview_code_python.png").write_bytes(
        render_code_card(
            "def shap_values(model, X):\n"
            "    explainer = shap.TreeExplainer(model)\n"
            "    return explainer(X)",
            language="python",
        )
    )
    print(f"Wrote previews to {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it**

```bash
python -m scripts.preview_card
```

Expected: three PNGs in `tmp/`. Open them and visually verify the cards are legible, on-brand, and the text doesn't get clipped.

- [ ] **Step 3: Commit (do not commit `tmp/`)**

```bash
git add scripts/preview_card.py
git commit -m "chore(scripts): add preview_card.py for local visual checks"
```

---

## Task 11: Final verification

- [ ] **Step 1: Run the full test suite**

```bash
pytest -q
```

Expected: all green, total > 70 tests.

- [ ] **Step 2: Lint + format + types**

```bash
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
mypy src/
```

Expected: all clean. If `ruff format --check` reports diffs, run `ruff format src/ tests/ scripts/` and commit the formatting separately.

- [ ] **Step 3: Manual dry run**

```bash
python -m agent draft --dry-run
```

Expected: prints a caption that follows the new voice (hook + whitespace + closer question), and prints "DRY RUN" without sending email. The dry-run path still skips persisting the draft so no PNG is left in `db/images/`.

- [ ] **Step 4: Push the branch**

```bash
git push origin phase-3-engagement
```

- [ ] **Step 5: Merge to main + cloud E2E test**

This step mirrors Phase 2's merge flow.

```bash
git checkout main
git pull --ff-only
git merge phase-3-engagement --no-ff -m "Merge phase-3-engagement: engagement voice + generated image cards"
git push origin main
```

Then in the GitHub UI (or via `gh`):

```bash
gh workflow run draft.yml --repo 99anujb/linkedin-agent --ref main
```

Watch the run:

```bash
gh run watch --repo 99anujb/linkedin-agent --exit-status
```

Expected:
- The "Run draft" step finishes green.
- A new `chore(image): card for draft <uuid>` commit lands on `main`.
- An email arrives in `99anujbansal@gmail.com` with the new hook-first voice and a generated card embedded.

- [ ] **Step 6: Click APPROVE in the email**

Open the email in Gmail, click APPROVE, confirm:
- Worker shows the blue "Draft approved" page.
- `post.yml` runs green.
- Buffer queue shows a scheduled post with the new image.

- [ ] **Step 7: Delete the merged branch**

```bash
git branch -d phase-3-engagement
git push origin --delete phase-3-engagement
```

Done.
