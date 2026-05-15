from __future__ import annotations

from pathlib import Path

from agent.generators.caption import generate_caption
from agent.sources.profile import SourceContent


class FakeAnthropicClient:
    """Mimics the Messages API surface we use."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []
        self.messages = self  # we use client.messages.create

    def create(self, **kwargs) -> object:
        self.calls.append(kwargs)

        class _Block:
            def __init__(self, t: str) -> None:
                self.type = "text"
                self.text = t

        class _Resp:
            def __init__(self, t: str) -> None:
                self.content = [_Block(t)]

        return _Resp(self._text)


def test_generate_caption_returns_text(tmp_path: Path) -> None:
    fixture = (Path(__file__).parent.parent / "fixtures" / "claude_caption.txt").read_text()
    client = FakeAnthropicClient(fixture)
    src = SourceContent(
        title="AFM Z-Height Map Reconstruction",
        body="Built a two-stage deep learning pipeline...",
        keywords=["PyTorch", "Attention U-Net"],
        source_ref="project:afm",
        metrics={"median_recovery": "97.1%", "mae_nm": 0.77},
    )
    out = generate_caption(
        client,
        post_type="project",
        source=src,
        role_targets=["Data Scientist"],
        model="claude-sonnet-4-6",
    )
    assert "97.1%" in out
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == "claude-sonnet-4-6"
    # message contains our voice guidelines + source body
    user_msg = client.calls[0]["messages"][0]["content"]
    assert "AFM" in user_msg
