from __future__ import annotations

import base64
import io

import pytest
import respx
from PIL import Image

from agent.generators.cloudflare_image import (
    API_BASE,
    DEFAULT_MODEL,
    CloudflareImageError,
    generate_image,
)


def _endpoint(account_id: str = "acct") -> str:
    return f"{API_BASE}/{account_id}/ai/run/{DEFAULT_MODEL}"


def _fake_jpeg_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(255, 0, 0)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@respx.mock
def test_generate_image_happy_path() -> None:
    route = respx.post(_endpoint()).respond(
        json={"success": True, "result": {"image": _fake_jpeg_b64()}}
    )
    png = generate_image("a robot", account_id="acct", api_token="tok")
    assert route.called
    # PNG magic header
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


@respx.mock
def test_generate_image_raises_on_4xx() -> None:
    respx.post(_endpoint()).respond(status_code=429, text="rate limited")
    with pytest.raises(CloudflareImageError):
        generate_image("prompt", account_id="acct", api_token="tok")


@respx.mock
def test_generate_image_raises_on_success_false() -> None:
    respx.post(_endpoint()).respond(
        json={"success": False, "errors": [{"message": "bad model"}]}
    )
    with pytest.raises(CloudflareImageError):
        generate_image("prompt", account_id="acct", api_token="tok")


@respx.mock
def test_generate_image_raises_when_no_image_field() -> None:
    respx.post(_endpoint()).respond(json={"success": True, "result": {}})
    with pytest.raises(CloudflareImageError):
        generate_image("prompt", account_id="acct", api_token="tok")


def test_missing_keys_raises() -> None:
    with pytest.raises(CloudflareImageError):
        generate_image("p", account_id="", api_token="tok")
    with pytest.raises(CloudflareImageError):
        generate_image("p", account_id="acct", api_token="")


@respx.mock
def test_uses_auth_header() -> None:
    route = respx.post(_endpoint()).respond(
        json={"success": True, "result": {"image": _fake_jpeg_b64()}}
    )
    generate_image("p", account_id="acct", api_token="secret123")
    assert route.called
    auth = route.calls.last.request.headers.get("authorization")
    assert auth == "Bearer secret123"
