"""Cloudflare Workers AI image generation: FLUX.1-schnell via REST.

Free tier on Workers AI covers daily post volume. Endpoint returns a
base64-encoded JPEG; we convert to PNG bytes to match the rest of the
pipeline. Caller is responsible for fallbacks.
"""

from __future__ import annotations

import base64
import io
import logging

import httpx
from PIL import Image

log = logging.getLogger(__name__)

DEFAULT_MODEL = "@cf/black-forest-labs/flux-1-schnell"
API_BASE = "https://api.cloudflare.com/client/v4/accounts"
TIMEOUT = 60.0


class CloudflareImageError(RuntimeError):
    """Raised when the Cloudflare Workers AI image API returns no usable image."""


def _endpoint(account_id: str, model: str) -> str:
    return f"{API_BASE}/{account_id}/ai/run/{model}"


def _jpeg_to_png(jpeg_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(jpeg_bytes)) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()


def generate_image(
    prompt: str,
    *,
    account_id: str,
    api_token: str,
    model: str = DEFAULT_MODEL,
    steps: int = 4,
    client: httpx.Client | None = None,
) -> bytes:
    """Generate a single image and return PNG bytes. Raises CloudflareImageError."""
    if not account_id or not api_token:
        raise CloudflareImageError("missing CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN")

    url = _endpoint(account_id, model)
    headers = {"Authorization": f"Bearer {api_token}"}
    body = {"prompt": prompt, "steps": steps}

    log.info("Calling Cloudflare Workers AI image (model=%s, steps=%d)", model, steps)
    try:
        if client is None:
            resp = httpx.post(url, json=body, headers=headers, timeout=TIMEOUT)
        else:
            resp = client.post(url, json=body, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise CloudflareImageError(f"Cloudflare image HTTP error: {e}") from e

    if resp.status_code >= 400:
        raise CloudflareImageError(
            f"Cloudflare image API {resp.status_code}: {resp.text[:300]}"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise CloudflareImageError(f"Cloudflare image response not JSON: {e}") from e

    if not payload.get("success", True):
        raise CloudflareImageError(f"Cloudflare image API errors: {payload.get('errors')}")

    result = payload.get("result") or {}
    b64 = result.get("image")
    if not b64:
        raise CloudflareImageError(f"Cloudflare image response had no image data: {payload}")

    try:
        jpeg_bytes = base64.b64decode(b64)
    except (ValueError, TypeError) as e:
        raise CloudflareImageError(f"Cloudflare image base64 decode failed: {e}") from e

    try:
        return _jpeg_to_png(jpeg_bytes)
    except Exception as e:
        raise CloudflareImageError(f"Cloudflare image PNG conversion failed: {e}") from e
