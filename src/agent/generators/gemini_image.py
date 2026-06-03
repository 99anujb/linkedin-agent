"""Gemini image generation: hero image from a text prompt.

Uses Google's free-tier Gemini native image generation via the
`generateContent` endpoint (model `gemini-2.5-flash-image` by default).
Returns raw PNG bytes. Caller is responsible for fallbacks.

The older `imagen-*` predict-style models are paid only and are not
used here.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash-image"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_ASPECT = "16:9"
TIMEOUT = 60.0


class GeminiImageError(RuntimeError):
    """Raised when the Gemini image API returns no usable image."""


def _endpoint(model: str, api_key: str) -> str:
    return f"{API_BASE}/{model}:generateContent?key={api_key}"


def _extract_image_bytes(payload: dict[str, Any]) -> bytes | None:
    """Walk the response and return raw bytes from the first inlineData part."""
    for cand in payload.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            data = part.get("inlineData") or part.get("inline_data")
            if not data:
                continue
            b64 = data.get("data")
            if b64:
                try:
                    return base64.b64decode(b64)
                except (ValueError, TypeError):
                    continue
    return None


def generate_image(
    prompt: str,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    aspect_ratio: str = DEFAULT_ASPECT,
    client: httpx.Client | None = None,
) -> bytes:
    """Generate a single image and return PNG bytes. Raises GeminiImageError."""
    if not api_key:
        raise GeminiImageError("missing GEMINI_API_KEY")

    full_prompt = f"{prompt}\n\nAspect ratio: {aspect_ratio}."
    body = {
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }

    url = _endpoint(model, api_key)
    log.info("Calling Gemini image (model=%s, aspect=%s)", model, aspect_ratio)
    try:
        if client is None:
            resp = httpx.post(url, json=body, timeout=TIMEOUT)
        else:
            resp = client.post(url, json=body, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise GeminiImageError(f"Gemini image HTTP error: {e}") from e

    if resp.status_code >= 400:
        raise GeminiImageError(f"Gemini image API {resp.status_code}: {resp.text[:300]}")

    try:
        payload = resp.json()
    except ValueError as e:
        raise GeminiImageError(f"Gemini image response not JSON: {e}") from e

    image_bytes = _extract_image_bytes(payload)
    if image_bytes is None:
        raise GeminiImageError(f"Gemini image response had no image data: {payload}")
    return image_bytes


def build_image_prompt(*, post_type: str, hook: str, keywords: list[str]) -> str:
    """Compose a topic-aware prompt for image generation."""
    style = (
        "Modern editorial illustration for a LinkedIn post. Clean, professional, "
        "vibrant but tasteful color palette. Minimal text, no logos, no captions, "
        "no watermarks, no copyrighted characters. 16:9 wide composition."
    )
    type_flavor = {
        "trending": "tech / AI news vibe, dynamic composition, suggests motion",
        "concept": "abstract conceptual illustration of a data idea, clear visual metaphor",
        "tutorial": "infographic feel with clean shapes representing steps",
        "roadmap": "path / journey metaphor, milestones, forward motion",
        "news_take": "editorial illustration framing a perspective, slight contrast",
        "career": "human, hopeful, growth-oriented illustration, warm tones",
        "project": "abstract data / science illustration tied to the project topic",
    }.get(post_type, "modern editorial illustration with a data theme")

    kw = ", ".join(k for k in keywords[:6] if k)
    hook_clean = " ".join(hook.split())[:160]
    return (
        f"{style} {type_flavor}. Subject: {hook_clean}. "
        f"Themes / keywords: {kw}. No text in the image."
    )
