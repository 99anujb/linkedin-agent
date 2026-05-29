from __future__ import annotations

import base64

import pytest
import respx

from agent.generators.gemini_image import (
    API_BASE,
    GeminiImageError,
    build_image_prompt,
    generate_image,
)


@respx.mock
def test_generate_image_happy_path() -> None:
    fake_png = b"\x89PNG\r\n\x1a\nhello"
    encoded = base64.b64encode(fake_png).decode("ascii")
    route = respx.post(f"{API_BASE}/imagen-3.0-generate-002:predict").respond(
        json={"predictions": [{"bytesBase64Encoded": encoded}]}
    )
    result = generate_image("a robot dreaming", api_key="key")
    assert route.called
    assert result == fake_png


@respx.mock
def test_generate_image_raises_on_4xx() -> None:
    respx.post(f"{API_BASE}/imagen-3.0-generate-002:predict").respond(
        status_code=400, json={"error": "bad"}
    )
    with pytest.raises(GeminiImageError):
        generate_image("prompt", api_key="key")


@respx.mock
def test_generate_image_raises_when_predictions_empty() -> None:
    respx.post(f"{API_BASE}/imagen-3.0-generate-002:predict").respond(json={"predictions": []})
    with pytest.raises(GeminiImageError):
        generate_image("prompt", api_key="key")


def test_missing_key_raises() -> None:
    with pytest.raises(GeminiImageError):
        generate_image("p", api_key="")


def test_build_prompt_includes_topic_flavor() -> None:
    prompt = build_image_prompt(
        post_type="trending",
        hook="Anthropic ships Claude 5",
        keywords=["AI", "Claude", "Anthropic"],
    )
    assert "Anthropic ships Claude 5" in prompt
    assert "16:9" in prompt
    assert "No text" in prompt


def test_build_prompt_unknown_type_gets_default_flavor() -> None:
    prompt = build_image_prompt(post_type="???", hook="Hook", keywords=["x"])
    assert "data theme" in prompt or "editorial" in prompt
