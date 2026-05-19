from __future__ import annotations

from agent.generators.prompts import (
    VOICE_GUIDELINES,
    build_caption_messages,
    parse_format_choice,
)
from agent.sources.profile import SourceContent


def _source() -> SourceContent:
    return SourceContent(
        source_ref="proj:fraud",
        title="Fraud detection model",
        body="Built an XGBoost classifier that reduced false positives by 38%.",
        keywords=["fraud", "xgboost", "ml"],
        metrics={"false_positive_reduction": "38%"},
    )


def test_voice_guidelines_enforces_engagement_rules() -> None:
    g = VOICE_GUIDELINES
    assert "Hook" in g
    assert "2 short lines" in g
    assert "700" in g and "1300" in g
    assert "blank line" in g.lower()
    assert "Avoid hype" in g or "avoid hype" in g.lower()


def test_build_caption_messages_includes_format_picker() -> None:
    msgs = build_caption_messages("project", _source(), ["Data Scientist"])
    content = msgs[0]["content"]
    assert "hot-take" in content
    assert "story" in content
    assert "list" in content
    assert "framework" in content
    assert "FORMAT:" in content
    assert "CAPTION:" in content


def test_parse_format_choice_extracts_picked_format_and_caption() -> None:
    raw = "FORMAT: list\nCAPTION:\nLine one.\n\nLine two.\n\nQ?"
    fmt, caption = parse_format_choice(raw)
    assert fmt == "list"
    assert caption.startswith("Line one.")
    assert "FORMAT:" not in caption


def test_parse_format_choice_falls_back_when_label_missing() -> None:
    raw = "Just a caption without labels.\n\nQ?"
    fmt, caption = parse_format_choice(raw)
    assert fmt == "framework"  # default
    assert caption == raw.strip()
