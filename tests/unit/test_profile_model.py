from pathlib import Path

import pytest

from agent.profile_model import Profile, load_profile


def test_load_profile_parses_sample(sample_profile_path: Path) -> None:
    profile = load_profile(sample_profile_path)
    assert isinstance(profile, Profile)
    assert profile.contact.name == "Test User"
    assert "Data Analyst" in profile.role_targets
    assert len(profile.projects) == 2
    assert profile.projects[0].framings["data_scientist"].startswith("Built")


def test_load_profile_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "missing.json")


def test_load_profile_malformed_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ValueError):
        load_profile(bad)
