from agent.generators.prompts import (
    VOICE_GUIDELINES,
    build_caption_messages,
    build_hashtag_messages,
)
from agent.sources.profile import SourceContent


def test_caption_messages_contain_voice_and_source() -> None:
    src = SourceContent(
        title="Project One",
        body="Built a deep learning thing with 95% accuracy.",
        keywords=["PyTorch", "ml"],
        source_ref="project:p1",
        metrics={"accuracy": "95%"},
    )
    msgs = build_caption_messages("project", src, role_targets=["Data Scientist"])
    assert len(msgs) >= 1
    user_text = "\n".join(m["content"] for m in msgs if m["role"] == "user")
    assert "Project One" in user_text
    assert "95%" in user_text
    assert "project" in user_text.lower()


def test_voice_guidelines_present() -> None:
    assert "metric" in VOICE_GUIDELINES.lower()
    assert "hashtags inline" in VOICE_GUIDELINES.lower()  # explicit no-inline rule


def test_hashtag_messages() -> None:
    msgs = build_hashtag_messages(
        post_type="project",
        caption="My new project on attention u-net achieved 97% recovery.",
        keywords=["Attention U-Net", "PyTorch"],
    )
    user_text = "\n".join(m["content"] for m in msgs if m["role"] == "user")
    assert "Attention U-Net" in user_text or "attention" in user_text.lower()
    assert "JSON" in user_text or "json" in user_text
