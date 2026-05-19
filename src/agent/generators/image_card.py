"""Pillow / Pygments image card renderers for LinkedIn posts."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pygments import highlight  # type: ignore[import-untyped]
from pygments.formatters.img import ImageFormatter  # type: ignore[import-untyped]
from pygments.lexers import get_lexer_by_name  # type: ignore[import-untyped]
from pygments.util import ClassNotFound  # type: ignore[import-untyped]

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
    assert pixels is not None
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


def _resize_to_card(img: Image.Image) -> Image.Image:
    """Center-paste the Pygments output onto a card-sized canvas."""
    canvas = _gradient_background(CARD_WIDTH, CARD_HEIGHT)
    snippet_max_w = CARD_WIDTH - _SIDE_PADDING * 2
    snippet_max_h = CARD_HEIGHT - _SIDE_PADDING * 2
    w, h = img.size
    scale = min(snippet_max_w / w, snippet_max_h / h, 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
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
        except Exception:
            log.warning("code card render failed; falling back to quote card")
    return render_quote_card(hook)
