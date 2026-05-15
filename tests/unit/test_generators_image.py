from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from agent.generators.image import FALLBACK_IMAGE_URL, ImageResult, fetch_image

FIXTURE = Path(__file__).parent.parent / "fixtures" / "unsplash_search.json"


@respx.mock
def test_fetch_image_success() -> None:
    body = json.loads(FIXTURE.read_text())
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(200, json=body)
    )
    result = fetch_image(keywords=["data science", "ml"], access_key="test-key")
    assert isinstance(result, ImageResult)
    assert result.url == "https://images.unsplash.com/regular"
    assert "Jane Doe" in result.credit
    assert "Unsplash" in result.credit


@respx.mock
def test_fetch_image_no_results_falls_back() -> None:
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    result = fetch_image(keywords=["zzz"], access_key="test-key")
    assert result.url == FALLBACK_IMAGE_URL
    assert "fallback" in result.credit.lower()


@respx.mock
def test_fetch_image_http_error_falls_back() -> None:
    respx.get("https://api.unsplash.com/search/photos").mock(
        return_value=httpx.Response(500, json={"errors": ["oops"]})
    )
    result = fetch_image(keywords=["x"], access_key="test-key")
    assert result.url == FALLBACK_IMAGE_URL
