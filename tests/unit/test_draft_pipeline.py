from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from agent.config import Settings
from agent.db.store import (
    get_rotation_state,
    init_db,
)
from agent.draft import DraftResult, run_draft
from agent.generators.image import ImageResult
from agent.generators.image_picker import ImageOutcome


@pytest.fixture
def settings(tmp_path: Path, sample_profile_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="x",
        unsplash_access_key="x",
        gmail_username="a@b.com",
        gmail_app_password="x",
        gmail_recipient="a@b.com",
        profile_path=sample_profile_path,
        db_path=tmp_path / "state.sqlite",
        log_level="INFO",
        buffer_access_token="btkn",
        buffer_linkedin_profile_id="p1",
        hmac_secret="secret-32-bytes-aaaaaaaaaaaaaaaa",
        approval_base_url="https://approval.example.workers.dev",
    )


def _wire_fakes():
    anthropic = MagicMock()

    def _block(text: str):
        return type("B", (), {"type": "text", "text": text})()

    anthropic.messages.create.side_effect = [
        # caption (with FORMAT label)
        MagicMock(content=[_block("FORMAT: list\nCAPTION:\nHook.\n\nBody.\n\nQ?")]),
        # hashtags
        MagicMock(content=[_block('["#A","#B","#C","#D","#E"]')]),
        # snippet (only used for project/concept post_type)
        MagicMock(content=[_block("LANGUAGE: sql\nCODE:\nSELECT 1;")]),
    ]
    image_fn = MagicMock(return_value=ImageResult(url="http://img", credit="cred"))
    send_fn = MagicMock()
    return anthropic, image_fn, send_fn


@freeze_time("2026-05-13T12:00:00Z")
def test_run_draft_happy_path(settings: Settings) -> None:
    # init DB once so paths exist
    conn = init_db(settings.db_path)
    conn.close()

    anthropic, image_fn, send_fn = _wire_fakes()

    result = run_draft(
        settings,
        anthropic_client=anthropic,
        image_fn=image_fn,
        email_send_fn=send_fn,
        today=date(2026, 5, 13),  # Wed → tutorial
    )
    assert isinstance(result, DraftResult)
    assert result.status == "drafted"
    assert result.post_type == "tutorial"

    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (result.draft_id,)).fetchone()
    assert row is not None
    assert row["status"] == "pending"
    assert row["post_type"] == "tutorial"
    rs = get_rotation_state(conn)
    assert rs.last_day == "2026-05-13"
    # tutorial advances the skill index (shared with concept).
    assert rs.skill_index == 1
    conn.close()

    # Verify email has real signed tokens (not placeholders)
    sent_args = send_fn.call_args
    sent_msg = sent_args.args[0] if sent_args.args else sent_args.kwargs.get("msg")
    assert sent_msg is not None
    html = sent_msg.get_body(preferencelist=("html",)).get_content()
    assert "approval.example.workers.dev/a?t=" in html
    assert "approval.example.workers.dev/r?t=" in html
    assert "placeholder" not in html

    send_fn.assert_called_once()

    # New: image_url should point to the GitHub raw base, not Unsplash
    assert row["image_url"].startswith(
        "https://raw.githubusercontent.com/99anujb/linkedin-agent/main/db/images/"
    )
    assert row["image_url"].endswith(".png")


@freeze_time("2026-05-13T12:00:00Z")
def test_run_draft_skips_when_already_drafted(settings: Settings) -> None:
    conn = init_db(settings.db_path)
    conn.execute("UPDATE rotation_state SET last_day = '2026-05-13' WHERE id = 1")
    conn.commit()
    conn.close()

    anthropic, image_fn, send_fn = _wire_fakes()
    result = run_draft(
        settings,
        anthropic_client=anthropic,
        image_fn=image_fn,
        email_send_fn=send_fn,
        today=date(2026, 5, 13),
    )
    assert result.status == "skipped"
    anthropic.messages.create.assert_not_called()
    send_fn.assert_not_called()


@freeze_time("2026-05-13T12:00:00Z")
def test_run_draft_uses_pick_image_url_outcome(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When pick_image returns a URL (Unsplash path), draft uses it directly."""
    init_db(settings.db_path).close()

    def _fake_pick(**_):
        return ImageOutcome(
            bytes_=None,
            url="https://images.unsplash.com/test.jpg",
            credit="Photo: Unsplash",
            strategy="unsplash",
        )

    monkeypatch.setattr("agent.draft.pick_image", _fake_pick)

    anthropic, image_fn, send_fn = _wire_fakes()
    result = run_draft(
        settings,
        anthropic_client=anthropic,
        image_fn=image_fn,
        email_send_fn=send_fn,
        today=date(2026, 5, 13),
    )
    assert result.status == "drafted"

    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (result.draft_id,)).fetchone()
    assert row["image_url"] == "https://images.unsplash.com/test.jpg"
    conn.close()


@freeze_time("2026-05-13T12:00:00Z")
def test_run_draft_dry_run_does_not_email_or_persist(settings: Settings) -> None:
    init_db(settings.db_path).close()
    anthropic, image_fn, send_fn = _wire_fakes()
    result = run_draft(
        settings,
        anthropic_client=anthropic,
        image_fn=image_fn,
        email_send_fn=send_fn,
        today=date(2026, 5, 13),
        dry_run=True,
    )
    assert result.status == "dry_run"
    send_fn.assert_not_called()
    conn = sqlite3.connect(settings.db_path)
    rows = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()
    assert rows[0] == 0
    rs = get_rotation_state(conn)
    assert rs.last_day is None
    conn.close()
