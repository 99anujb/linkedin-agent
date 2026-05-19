from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.generators.snippet import generate_snippet


def _mock_anthropic(text: str) -> MagicMock:
    block = type("B", (), {"type": "text", "text": text})()
    client = MagicMock()
    client.messages.create.return_value = MagicMock(content=[block])
    return client


def test_generate_snippet_parses_language_and_body() -> None:
    raw = "LANGUAGE: sql\nCODE:\nSELECT user_id, SUM(amount)\nFROM orders\nGROUP BY user_id;"
    client = _mock_anthropic(raw)
    snippet, language = generate_snippet(
        client, caption="window functions explainer", post_type="concept"
    )
    assert language == "sql"
    assert "SELECT" in snippet
    assert "LANGUAGE:" not in snippet
    assert "CODE:" not in snippet


def test_generate_snippet_defaults_language_when_missing() -> None:
    raw = "SELECT 1;"
    client = _mock_anthropic(raw)
    snippet, language = generate_snippet(
        client, caption="x", post_type="concept"
    )
    assert language == "text"
    assert snippet == "SELECT 1;"


def test_generate_snippet_empty_response_raises() -> None:
    client = _mock_anthropic("")
    with pytest.raises(ValueError):
        generate_snippet(client, caption="x", post_type="concept")
