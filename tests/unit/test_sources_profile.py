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


def test_tip_source(profile: Profile) -> None:
    src = build_source(RotationDecision("tip", "co_a"), profile)
    assert "Co A" in src.body
    assert src.source_ref == "tip:co_a"


def test_unknown_type_raises(profile: Profile) -> None:
    with pytest.raises(ValueError):
        build_source(RotationDecision("commentary", None), profile)
