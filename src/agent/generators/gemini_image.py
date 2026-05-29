"""Gemini Imagen client: generate a LinkedIn hero image from a prompt.

Uses the Generative Language API (https://generativelanguage.googleapis.com).
Returns raw PNG bytes. Caller is responsible for fallbacks.
"""

from __future__ import annotations

import base64
import logging

import httpx

log = logging.getLogger(__name__)

DEFAULT_MODEL = "imagen-3.0-generate-002"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_ASPECT = "16:9"
TIMEOUT = 60.0


class GeminiImageError(RuntimeError):
    """Raised when Imagen returns no usable image."""


def _endpoint(model: str, api_key: str) -> str:
    return f"{API_BASE}/{model}:predict?key={api_key}"


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

    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": aspect_ratio,
            "personGeneration": "allow_adult",
        },
    }

    url = _endpoint(model, api_key)
    log.info("Calling Imagen (model=%s, aspect=%s)", model, aspect_ratio)
    try:
        if client is None:
            resp = httpx.post(url, json=body, timeout=TIMEOUT)
        else:
            resp = client.post(url, json=body, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise GeminiImageError(f"Imagen HTTP error: {e}") from e

    if resp.status_code >= 400:
        raise GeminiImageError(f"Imagen API {resp.status_code}: {resp.text[:300]}")

    try:
        payload = resp.json()
    except ValueError as e:
        raise GeminiImageError(f"Imagen response not JSON: {e}") from e

    preds = payload.get("predictions") or []
    if not preds:
        raise GeminiImageError(f"Imagen returned no predictions: {payload}")

    b64 = preds[0].get("bytesBase64Encoded") or preds[0].get("image", {}).get("bytesBase64Encoded")
    if not b64:
        raise GeminiImageError(f"Imagen prediction missing image bytes: {preds[0]}")

    return base64.b64decode(b64)


def build_image_prompt(*, post_type: str, hook: str, keywords: list[str]) -> str:
    """Compose a topic-aware prompt for Imagen given the post context."""
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
