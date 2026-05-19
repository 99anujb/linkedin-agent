"""Generate a LinkedIn caption via Anthropic's Messages API."""

from __future__ import annotations

import logging
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from agent.generators.prompts import build_caption_messages, parse_format_choice
from agent.sources.profile import SourceContent

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

log = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    reraise=True,
)
def generate_caption(
    client: Any,
    *,
    post_type: str,
    source: SourceContent,
    role_targets: list[str],
    model: str = DEFAULT_MODEL,
) -> str:
    """Call Claude and return the caption text.

    `client` is an `anthropic.Anthropic` instance (or a duck-typed test double).
    """
    messages = build_caption_messages(post_type, source, role_targets)
    log.info("Generating caption (model=%s, post_type=%s)", model, post_type)
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=messages,
    )
    raw = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()
    _fmt, caption = parse_format_choice(raw)
    return caption
