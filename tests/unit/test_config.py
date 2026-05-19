import os
from pathlib import Path

import pytest

from agent.config import Settings, load_settings


def _full_env() -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": "sk-test",
        "UNSPLASH_ACCESS_KEY": "u-test",
        "GMAIL_USERNAME": "a@b.com",
        "GMAIL_APP_PASSWORD": "app-pwd",
        "GMAIL_RECIPIENT": "a@b.com",
        "PROFILE_PATH": "./master_profile.json",
        "DB_PATH": "./db/state.sqlite",
        "LOG_LEVEL": "INFO",
        "BUFFER_ACCESS_TOKEN": "btkn",
        "BUFFER_LINKEDIN_PROFILE_ID": "p1",
        "HMAC_SECRET": "secret-32-bytes-aaaaaaaaaaaaaaaa",
        "APPROVAL_BASE_URL": "https://approval.example.workers.dev",
    }


def test_load_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _full_env().items():
        monkeypatch.setenv(k, v)
    s = load_settings()
    assert isinstance(s, Settings)
    assert s.anthropic_api_key == "sk-test"
    assert s.gmail_recipient == "a@b.com"
    assert s.profile_path == Path("./master_profile.json")
    assert s.db_path == Path("./db/state.sqlite")
    assert s.log_level == "INFO"


def test_missing_required_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Prevent load_dotenv from re-populating from a local .env file.
    monkeypatch.setattr("agent.config.load_dotenv", lambda *a, **kw: None)
    env = _full_env()
    env.pop("ANTHROPIC_API_KEY")
    for k in list(os.environ):
        if k.startswith(("ANTHROPIC_", "UNSPLASH_", "GMAIL_", "PROFILE_", "DB_", "LOG_")):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        load_settings()


def test_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _full_env()
    env.pop("LOG_LEVEL")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    s = load_settings()
    assert s.log_level == "INFO"


def test_settings_includes_phase2_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _full_env()
    env.update(
        {
            "POST_LOCAL_TIMEZONE": "America/New_York",
            "POST_LOCAL_TIME": "11:00",
        }
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = load_settings()
    assert s.buffer_access_token == "btkn"
    assert s.buffer_linkedin_profile_id == "p1"
    assert s.hmac_secret == "secret-32-bytes-aaaaaaaaaaaaaaaa"
    assert s.approval_base_url == "https://approval.example.workers.dev"
    assert s.post_local_timezone == "America/New_York"
    assert s.post_local_time == "11:00"


def test_post_local_fields_default(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _full_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for k in ("POST_LOCAL_TIMEZONE", "POST_LOCAL_TIME"):
        monkeypatch.delenv(k, raising=False)
    s = load_settings()
    assert s.post_local_timezone == "America/New_York"
    assert s.post_local_time == "11:00"


def test_settings_has_github_raw_base_default(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _full_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GITHUB_RAW_BASE", raising=False)
    s = load_settings()
    assert s.github_raw_base == "https://raw.githubusercontent.com/99anujb/linkedin-agent/main"
