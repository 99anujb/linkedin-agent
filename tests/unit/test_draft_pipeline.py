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

    class _Block:
        type = "text"

    block = _Block()
    block.text = "Hook.\n\nBody.\n\nQ?"
    anthropic.messages.create.side_effect = [
        MagicMock(content=[block]),
        MagicMock(
            content=[type("B", (), {"type": "text", "text": '["#A","#B","#C","#D","#E"]'})()]
        ),
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
        today=date(2026, 5, 13),  # Wed → career
    )
    assert isinstance(result, DraftResult)
    assert result.status == "drafted"
    assert result.post_type == "career"

    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (result.draft_id,)).fetchone()
    assert row is not None
    assert row["status"] == "pending"
    assert row["post_type"] == "career"
    rs = get_rotation_state(conn)
    assert rs.last_day == "2026-05-13"
    assert rs.exp_index == 1
    conn.close()

    # Verify email has real signed tokens (not placeholders)
    sent_args = send_fn.call_args
    sent_msg = sent_args.args[0] if sent_args.args else sent_args.kwargs.get("msg")
    assert sent_msg is not None
    html = sent_msg.get_body(preferencelist=("html",)).get_content()
    assert "approval.example.workers.dev/a?t=" in html
    assert "approval.example.workers.dev/r?t=" in html
    assert "placeholder" not in html

    image_fn.assert_called_once()
    send_fn.assert_called_once()


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
