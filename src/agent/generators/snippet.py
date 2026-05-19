"""Generate a tiny code / SQL / data snippet illustrating the caption."""

from __future__ import annotations

import logging
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 512

log = logging.getLogger(__name__)

_PROMPT = """\
Given the LinkedIn caption below, output a tiny illustrative code or data
snippet (at most 15 lines) that supports the caption's technical claim.
Pick whichever language matches: sql, python, json, yaml, bash, text.

Output format (exactly):
LANGUAGE: <one of: sql | python | json | yaml | bash | text>
CODE:
<the snippet, no markdown fences>

If no code helps the caption, output:
LANGUAGE: text
CODE:
<a 1-3 line plain-text illustration instead>

Post type: {post_type}
Caption:
{caption}"""


def _build_messages(*, caption: str, post_type: str) -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": _PROMPT.format(post_type=post_type, caption=caption),
        }
    ]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    reraise=True,
)
def generate_snippet(
    client: Any,
    *,
    caption: str,
    post_type: str,
    model: str = DEFAULT_MODEL,
) -> tuple[str, str]:
    """Return `(snippet_text, language)`. Raises ValueError on empty response."""
    log.info("Generating snippet (model=%s, post_type=%s)", model, post_type)
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=_build_messages(caption=caption, post_type=post_type),
    )
    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()
    if not raw:
        raise ValueError("snippet generator returned empty response")
    if not raw.startswith("LANGUAGE:"):
        return raw, "text"
    head, _, tail = raw.partition("\nCODE:")
    language = head.removeprefix("LANGUAGE:").strip().lower() or "text"
    snippet = tail.strip()
    if not snippet:
        return raw, "text"
    return snippet, language
