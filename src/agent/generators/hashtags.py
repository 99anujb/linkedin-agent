"""Generate LinkedIn hashtags via Claude Haiku (cheap, fast)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agent.generators.prompts import build_hashtag_messages

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 256

log = logging.getLogger(__name__)


def _strip_codefence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    return m.group(1) if m else text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=16),
    retry=retry_if_not_exception_type(ValueError),
    reraise=True,
)
def generate_hashtags(
    client: Any,
    *,
    post_type: str,
    caption: str,
    keywords: list[str],
    model: str = DEFAULT_MODEL,
) -> list[str]:
    """Return 5–8 hashtags. Raises ValueError if Claude's response is unparseable."""
    messages = build_hashtag_messages(post_type, caption, keywords)
    log.info("Generating hashtags (model=%s)", model)
    resp = client.messages.create(model=model, max_tokens=MAX_TOKENS, messages=messages)
    raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    payload = _strip_codefence(raw).strip()
    try:
        tags = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ValueError(f"Hashtags response not JSON: {raw!r}") from e
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError(f"Hashtags response not list[str]: {tags!r}")
    return [t if t.startswith("#") else f"#{t}" for t in tags]


def format_hashtags(tags: list[str]) -> str:
    """Join hashtags into the single-line string used in the post body."""
    return " ".join(tags)
