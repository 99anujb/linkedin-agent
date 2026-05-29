from __future__ import annotations

import pytest

from agent.profile_model import Profile, load_profile
from agent.rotation import RotationDecision
from agent.sources.profile import SourceContent, build_source


@pytest.fixture
def profile(sample_profile_path) -> Profile:
    return load_profile(sample_profile_path)


def test_project_source(profile: Profile) -> None:
    src = build_source(RotationDecision("project", "p1"), profile)
    assert isinstance(src, SourceContent)
    assert src.title == "Project One"
    assert "95%" in src.body or "95" in src.body
    assert "PyTorch" in src.keywords
    assert src.source_ref == "project:p1"


def test_project_missing_id_falls_back_to_first(profile: Profile) -> None:
    src = build_source(RotationDecision("project", "nope"), profile)
    assert src.source_ref == "project:p1"


def test_concept_source(profile: Profile) -> None:
    # sub_key is a skills category key
    src = build_source(RotationDecision("concept", "machine_learning"), profile)
    assert "XGBoost" in src.body
    assert src.source_ref == "concept:machine_learning"
    assert "machine_learning" in src.keywords or "XGBoost" in src.keywords


def test_career_source(profile: Profile) -> None:
    src = build_source(RotationDecision("career", "achv_0"), profile)
    assert "Won a competition" in src.body  # from sample fixture
    assert src.source_ref.startswith("career:")
    assert "career" in src.keywords


def test_unknown_type_raises(profile: Profile) -> None:
    with pytest.raises(ValueError):
        build_source(RotationDecision("commentary", None), profile)


def test_tutorial_source(profile: Profile) -> None:
    src = build_source(RotationDecision("tutorial", "machine_learning"), profile)
    assert src.source_ref == "tutorial:machine_learning"
    assert "tutorial" in src.keywords or "how-to" in src.keywords
    assert "machine_learning" in src.body or "XGBoost" in src.body


def test_roadmap_source(profile: Profile) -> None:
    src = build_source(RotationDecision("roadmap", "Data Scientist"), profile)
    assert "roadmap" in src.keywords
    assert "Data Scientist" in src.body
    assert src.source_ref == "roadmap:data_scientist"


def test_trending_needs_conn(profile: Profile) -> None:
    with pytest.raises(ValueError):
        build_source(RotationDecision("trending", None), profile)


def test_trending_with_fake_headline(profile: Profile, tmp_db, monkeypatch) -> None:
    from agent.sources import rss

    fake = rss.Headline(
        title="Anthropic releases new Claude",
        summary="Claude got better at code.",
        link="https://anthropic.com/news",
        source="Anthropic News",
    )
    monkeypatch.setattr(
        "agent.sources.profile.pick_fresh_headline",
        lambda conn, **_: fake,
    )
    src = build_source(RotationDecision("trending", None), profile, conn=tmp_db)
    assert "Anthropic releases new Claude" in src.body
    assert src.source_ref.startswith("trending:")


def test_news_take_falls_back_when_no_headline(profile: Profile, tmp_db, monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.sources.profile.pick_fresh_headline",
        lambda conn, **_: None,
    )
    src = build_source(RotationDecision("news_take", None), profile, conn=tmp_db)
    # falls back to a concept source so the day still produces a post.
    assert src.source_ref.startswith("concept:")
