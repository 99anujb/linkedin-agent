from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from agent.generators.image import (
    BROAD_FALLBACK_QUERIES,
    FALLBACK_IMAGE_URL,
    ImageResult,
    _clean_keywords,
    _pick_broad_query,
    fetch_image,
)

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
def test_fetch_image_no_results_then_broad_retry_succeeds() -> None:
    body = json.loads(FIXTURE.read_text())
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        # First call (primary query) → empty. Second call (broad retry) → hit.
        if call_count["n"] == 1:
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json=body)

    respx.get("https://api.unsplash.com/search/photos").mock(side_effect=handler)
    result = fetch_image(keywords=["zzz"], access_key="test-key")
    assert call_count["n"] == 2
    assert result.url == "https://images.unsplash.com/regular"


@respx.mock
def test_fetch_image_both_empty_falls_back() -> None:
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


def test_clean_keywords_strips_underscores_and_hyphens() -> None:
    assert _clean_keywords(["visualization_bi", "data-science", "ml", "  ", ""]) == [
        "visualization bi",
        "data science",
        "ml",
    ]


def test_pick_broad_query_deterministic_and_in_pool() -> None:
    q1 = _pick_broad_query("trending ai today")
    q2 = _pick_broad_query("trending ai today")
    q3 = _pick_broad_query("completely different seed")
    assert q1 == q2
    assert q1 in BROAD_FALLBACK_QUERIES
    assert q3 in BROAD_FALLBACK_QUERIES


@respx.mock
def test_fetch_image_sanitizes_underscore_in_query() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = request.url.params.get("query", "")
        body = json.loads(FIXTURE.read_text())
        return httpx.Response(200, json=body)

    respx.get("https://api.unsplash.com/search/photos").mock(side_effect=handler)
    fetch_image(keywords=["visualization_bi", "Tableau"], access_key="test-key")
    assert "_" not in captured["query"]
    assert "visualization bi" in captured["query"]
