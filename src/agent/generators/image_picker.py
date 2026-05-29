"""Pick the right image strategy per post type with safe fallbacks.

Order per type:
  trending / concept / news_take      → Gemini Imagen → Unsplash → quote card
  tutorial                            → code card → Gemini Imagen → quote card
  roadmap                             → quote card → Gemini Imagen → Unsplash
  career                              → Unsplash → quote card
  project                             → code card → Unsplash → quote card

Returned tuple: (image_bytes_or_None, image_url_or_None, credit, strategy).
- If `image_bytes` is not None, caller should write it to disk + git-publish.
- If `image_url` is not None, caller uses it directly (Unsplash).
Exactly one of (image_bytes, image_url) is set.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from agent.generators.gemini_image import (
    GeminiImageError,
    build_image_prompt,
    generate_image,
)
from agent.generators.image import ImageResult, fetch_image
from agent.generators.image_card import render_code_card, render_quote_card

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageOutcome:
    bytes_: bytes | None
    url: str | None
    credit: str
    strategy: str


UnsplashFn = Callable[..., ImageResult]
GeminiFn = Callable[..., bytes]


def _try_gemini(
    *,
    post_type: str,
    hook: str,
    keywords: list[str],
    api_key: str | None,
    gemini_fn: GeminiFn,
) -> bytes | None:
    if not api_key:
        return None
    prompt = build_image_prompt(post_type=post_type, hook=hook, keywords=keywords)
    try:
        return gemini_fn(prompt, api_key=api_key)
    except GeminiImageError as e:
        log.warning("Gemini image failed: %s", e)
        return None
    except Exception as e:
        log.warning("Gemini image unexpected error: %s", e)
        return None


def _try_unsplash(
    *, keywords: list[str], access_key: str | None, unsplash_fn: UnsplashFn
) -> ImageResult | None:
    if not access_key:
        return None
    try:
        return unsplash_fn(keywords=keywords, access_key=access_key)
    except Exception as e:
        log.warning("Unsplash failed: %s", e)
        return None


def _try_code_card(snippet: str | None, language: str | None) -> bytes | None:
    if not snippet or not language:
        return None
    try:
        return render_code_card(snippet, language=language)
    except Exception as e:
        log.warning("code card render failed: %s", e)
        return None


def _quote_card(hook: str) -> bytes:
    return render_quote_card(hook)


def pick_image(
    *,
    post_type: str,
    hook: str,
    keywords: list[str],
    snippet: str | None,
    language: str | None,
    gemini_api_key: str | None,
    unsplash_access_key: str | None,
    gemini_fn: GeminiFn = generate_image,
    unsplash_fn: UnsplashFn = fetch_image,
) -> ImageOutcome:
    """Run the per-type fallback chain. Always returns a usable outcome."""

    gemini_first = {"trending", "concept", "news_take"}
    code_first = {"tutorial", "project"}
    quote_first = {"roadmap"}
    unsplash_first = {"career"}

    if post_type in gemini_first:
        b = _try_gemini(
            post_type=post_type,
            hook=hook,
            keywords=keywords,
            api_key=gemini_api_key,
            gemini_fn=gemini_fn,
        )
        if b:
            return ImageOutcome(
                bytes_=b, url=None, credit="Image: Gemini Imagen", strategy="gemini"
            )
        un = _try_unsplash(
            keywords=keywords, access_key=unsplash_access_key, unsplash_fn=unsplash_fn
        )
        if un:
            return ImageOutcome(bytes_=None, url=un.url, credit=un.credit, strategy="unsplash")
        return ImageOutcome(
            bytes_=_quote_card(hook), url=None, credit="Generated quote card", strategy="quote"
        )

    if post_type in code_first:
        b = _try_code_card(snippet, language)
        if b:
            return ImageOutcome(bytes_=b, url=None, credit="Generated code card", strategy="code")
        # For tutorials try Gemini next; for project posts try Unsplash next.
        if post_type == "tutorial":
            b2 = _try_gemini(
                post_type=post_type,
                hook=hook,
                keywords=keywords,
                api_key=gemini_api_key,
                gemini_fn=gemini_fn,
            )
            if b2:
                return ImageOutcome(
                    bytes_=b2, url=None, credit="Image: Gemini Imagen", strategy="gemini"
                )
        un = _try_unsplash(
            keywords=keywords, access_key=unsplash_access_key, unsplash_fn=unsplash_fn
        )
        if un:
            return ImageOutcome(bytes_=None, url=un.url, credit=un.credit, strategy="unsplash")
        return ImageOutcome(
            bytes_=_quote_card(hook), url=None, credit="Generated quote card", strategy="quote"
        )

    if post_type in quote_first:
        # roadmap: prefer the on-brand quote card (looks like an infographic),
        # then Gemini, then Unsplash.
        b = _quote_card(hook)
        return ImageOutcome(bytes_=b, url=None, credit="Generated quote card", strategy="quote")

    if post_type in unsplash_first:
        un = _try_unsplash(
            keywords=keywords, access_key=unsplash_access_key, unsplash_fn=unsplash_fn
        )
        if un:
            return ImageOutcome(bytes_=None, url=un.url, credit=un.credit, strategy="unsplash")
        return ImageOutcome(
            bytes_=_quote_card(hook), url=None, credit="Generated quote card", strategy="quote"
        )

    # Unknown post_type → safe quote card.
    return ImageOutcome(
        bytes_=_quote_card(hook), url=None, credit="Generated quote card", strategy="quote"
    )
