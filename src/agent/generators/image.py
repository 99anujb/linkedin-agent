"""Pick an image from Unsplash search results, with a stock fallback."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

import httpx

FALLBACK_IMAGE_URL = (
    "https://images.unsplash.com/photo-1551288049-bebda4e38f71" "?w=1200&auto=format&fit=crop&q=80"
)
FALLBACK_CREDIT = "Photo: Unsplash (fallback stock)"
UNSPLASH_SEARCH = "https://api.unsplash.com/search/photos"

BROAD_FALLBACK_QUERIES = (
    "technology",
    "data science",
    "artificial intelligence",
    "computer code",
    "abstract tech",
    "neural network",
    "machine learning",
    "futuristic technology",
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageResult:
    url: str
    credit: str


def _credit(user: dict[str, Any], photo_link: str) -> str:
    name = user.get("name") or user.get("username") or "Unsplash photographer"
    return f"Photo by {name} on Unsplash ({photo_link})"


def _clean_keywords(keywords: list[str]) -> list[str]:
    out: list[str] = []
    for k in keywords:
        cleaned = k.replace("_", " ").replace("-", " ").strip()
        if cleaned:
            out.append(cleaned)
    return out


def _pick_broad_query(seed: str) -> str:
    h = hashlib.md5(seed.encode("utf-8")).digest()[0]
    return BROAD_FALLBACK_QUERIES[h % len(BROAD_FALLBACK_QUERIES)]


def _unsplash_search(query: str, access_key: str) -> list[dict[str, Any]] | None:
    try:
        resp = httpx.get(
            UNSPLASH_SEARCH,
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Unsplash fetch failed for %r: %s", query, e)
        return None
    return data.get("results") or []


def _first_result(results: list[dict[str, Any]]) -> ImageResult:
    first = results[0]
    url = first["urls"]["regular"]
    credit = _credit(first.get("user", {}), first.get("links", {}).get("html", ""))
    return ImageResult(url, credit)


def fetch_image(*, keywords: list[str], access_key: str) -> ImageResult:
    """Search Unsplash; retry with a broad query on empty; hardcoded fallback last."""
    cleaned = _clean_keywords(keywords)
    primary_query = " ".join(cleaned[:3]) or "technology"

    results = _unsplash_search(primary_query, access_key)
    if results is None:
        return ImageResult(FALLBACK_IMAGE_URL, FALLBACK_CREDIT)
    if results:
        return _first_result(results)

    broad = _pick_broad_query(primary_query)
    log.info(
        "Unsplash returned no results for %r — retrying with broad query %r",
        primary_query,
        broad,
    )
    retry = _unsplash_search(broad, access_key)
    if retry:
        return _first_result(retry)

    log.info("Unsplash retry also empty for %r — using hardcoded fallback", broad)
    return ImageResult(FALLBACK_IMAGE_URL, FALLBACK_CREDIT)
