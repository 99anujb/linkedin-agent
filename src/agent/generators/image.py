"""Pick an image from Unsplash search results, with a stock fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

FALLBACK_IMAGE_URL = (
    "https://images.unsplash.com/photo-1551288049-bebda4e38f71"
    "?w=1200&auto=format&fit=crop&q=80"
)
FALLBACK_CREDIT = "Photo: Unsplash (fallback stock)"
UNSPLASH_SEARCH = "https://api.unsplash.com/search/photos"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageResult:
    url: str
    credit: str


def _credit(user: dict, photo_link: str) -> str:
    name = user.get("name") or user.get("username") or "Unsplash photographer"
    return f"Photo by {name} on Unsplash ({photo_link})"


def fetch_image(*, keywords: list[str], access_key: str) -> ImageResult:
    """Search Unsplash; return first result or a fallback on error/empty."""
    query = " ".join(keywords[:3]) or "technology"
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
        log.warning("Unsplash fetch failed: %s — using fallback", e)
        return ImageResult(FALLBACK_IMAGE_URL, FALLBACK_CREDIT)

    results = data.get("results") or []
    if not results:
        log.info("Unsplash returned no results for %r — using fallback", query)
        return ImageResult(FALLBACK_IMAGE_URL, FALLBACK_CREDIT)
    first = results[0]
    url = first["urls"]["regular"]
    credit = _credit(first.get("user", {}), first.get("links", {}).get("html", ""))
    return ImageResult(url, credit)
