from __future__ import annotations

from typing import Any

import pytest

from agent.generators.image import ImageResult
from agent.generators.image_picker import ImageOutcome, pick_image


def _ok_gemini(prompt: str, *, api_key: str, **_: Any) -> bytes:
    assert api_key == "gkey"
    assert prompt
    return b"\x89PNG\r\n\x1a\nfake"


def _fail_gemini(prompt: str, *, api_key: str, **_: Any) -> bytes:
    raise RuntimeError("gemini down")


def _ok_unsplash(*, keywords: list[str], access_key: str) -> ImageResult:
    assert access_key == "ukey"
    return ImageResult(url="https://images.unsplash.com/x.jpg", credit="Photo: Unsplash")


def _fail_unsplash(*, keywords: list[str], access_key: str) -> ImageResult:
    raise RuntimeError("unsplash down")


@pytest.mark.parametrize("post_type", ["trending", "concept", "news_take"])
def test_gemini_first_types(post_type: str) -> None:
    outcome = pick_image(
        post_type=post_type,
        hook="Hook text",
        keywords=["AI", "data"],
        snippet=None,
        language=None,
        gemini_api_key="gkey",
        unsplash_access_key="ukey",
        gemini_fn=_ok_gemini,
        unsplash_fn=_ok_unsplash,
    )
    assert outcome.strategy == "gemini"
    assert outcome.bytes_ is not None
    assert outcome.url is None


def test_gemini_falls_back_to_unsplash_when_gemini_fails() -> None:
    outcome = pick_image(
        post_type="trending",
        hook="Hook",
        keywords=["AI"],
        snippet=None,
        language=None,
        gemini_api_key="gkey",
        unsplash_access_key="ukey",
        gemini_fn=_fail_gemini,
        unsplash_fn=_ok_unsplash,
    )
    assert outcome.strategy == "unsplash"
    assert outcome.url == "https://images.unsplash.com/x.jpg"


def test_gemini_falls_back_to_quote_card_when_both_fail() -> None:
    outcome = pick_image(
        post_type="trending",
        hook="Hook on a single line",
        keywords=["AI"],
        snippet=None,
        language=None,
        gemini_api_key="gkey",
        unsplash_access_key="ukey",
        gemini_fn=_fail_gemini,
        unsplash_fn=_fail_unsplash,
    )
    assert outcome.strategy == "quote"
    assert outcome.bytes_ is not None


def test_tutorial_prefers_code_card_when_snippet_present() -> None:
    outcome = pick_image(
        post_type="tutorial",
        hook="Hook",
        keywords=["sql"],
        snippet="SELECT 1;",
        language="sql",
        gemini_api_key="gkey",
        unsplash_access_key="ukey",
        gemini_fn=_ok_gemini,
        unsplash_fn=_ok_unsplash,
    )
    assert outcome.strategy == "code"


def test_tutorial_falls_back_to_gemini_without_snippet() -> None:
    outcome = pick_image(
        post_type="tutorial",
        hook="Hook",
        keywords=["sql"],
        snippet=None,
        language=None,
        gemini_api_key="gkey",
        unsplash_access_key="ukey",
        gemini_fn=_ok_gemini,
        unsplash_fn=_ok_unsplash,
    )
    assert outcome.strategy == "gemini"


def test_project_prefers_code_card_then_unsplash() -> None:
    # No snippet → skip code; gemini disabled by missing key → unsplash.
    outcome = pick_image(
        post_type="project",
        hook="Hook",
        keywords=["ml"],
        snippet=None,
        language=None,
        gemini_api_key=None,
        unsplash_access_key="ukey",
        gemini_fn=_ok_gemini,
        unsplash_fn=_ok_unsplash,
    )
    assert outcome.strategy == "unsplash"


def test_roadmap_uses_quote_card() -> None:
    outcome = pick_image(
        post_type="roadmap",
        hook="Hook",
        keywords=["career"],
        snippet=None,
        language=None,
        gemini_api_key="gkey",
        unsplash_access_key="ukey",
        gemini_fn=_ok_gemini,
        unsplash_fn=_ok_unsplash,
    )
    assert outcome.strategy == "quote"
    assert outcome.bytes_ is not None


def test_career_uses_unsplash_first() -> None:
    outcome = pick_image(
        post_type="career",
        hook="Hook",
        keywords=["growth"],
        snippet=None,
        language=None,
        gemini_api_key="gkey",
        unsplash_access_key="ukey",
        gemini_fn=_ok_gemini,
        unsplash_fn=_ok_unsplash,
    )
    assert outcome.strategy == "unsplash"


def test_gemini_skipped_when_no_api_key() -> None:
    outcome = pick_image(
        post_type="trending",
        hook="Hook",
        keywords=["AI"],
        snippet=None,
        language=None,
        gemini_api_key=None,
        unsplash_access_key="ukey",
        gemini_fn=_ok_gemini,
        unsplash_fn=_ok_unsplash,
    )
    assert outcome.strategy == "unsplash"


def test_outcome_dataclass_round_trip() -> None:
    o = ImageOutcome(bytes_=b"x", url=None, credit="c", strategy="s")
    assert o.bytes_ == b"x"
    assert o.url is None
