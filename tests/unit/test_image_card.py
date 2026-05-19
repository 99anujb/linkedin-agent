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
