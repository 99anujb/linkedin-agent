from __future__ import annotations

from pathlib import Path

import pytest

from agent.generators.hashtags import format_hashtags, generate_hashtags


class FakeClient:
    def __init__(self, raw: str) -> None:
        self._raw = raw
        self.messages = self
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class _Block:
            type = "text"

            def __init__(self, t: str) -> None:
                self.text = t

        class _Resp:
            def __init__(self, t: str) -> None:
                self.content = [_Block(t)]

        return _Resp(self._raw)


def test_generate_hashtags_parses_json() -> None:
    raw = (Path(__file__).parent.parent / "fixtures" / "claude_hashtags.json").read_text()
    client = FakeClient(raw)
    tags = generate_hashtags(
        client,
        post_type="project",
        caption="A caption about deep learning.",
        keywords=["PyTorch"],
        model="claude-haiku-4-5-20251001",
    )
    assert tags[0].startswith("#")
    assert 5 <= len(tags) <= 8
    assert "#DataScience" in tags
    assert client.calls[0]["model"] == "claude-haiku-4-5-20251001"


def test_generate_hashtags_strips_codefence() -> None:
    client = FakeClient('```json\n["#A", "#B", "#C", "#D", "#E"]\n```')
    tags = generate_hashtags(client, post_type="tip", caption="x", keywords=[])
    assert tags == ["#A", "#B", "#C", "#D", "#E"]


def test_generate_hashtags_raises_on_garbage() -> None:
    client = FakeClient("not json at all")
    with pytest.raises(ValueError):
        generate_hashtags(client, post_type="tip", caption="x", keywords=[])


def test_format_hashtags() -> None:
    assert format_hashtags(["#A", "#B", "#C"]) == "#A #B #C"
