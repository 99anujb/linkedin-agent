from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from agent.config import Settings
from agent.db.store import Draft, get_draft, init_db, insert_draft
from agent.post import PostResult, next_scheduled_at_utc, run_post


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
        hmac_secret="s",
        approval_base_url="https://x",
        post_local_timezone="America/New_York",
        post_local_time="11:00",
    )


def _seed_draft(db_path: Path, status: str = "pending") -> str:
    conn = init_db(db_path)
    insert_draft(
        conn,
        Draft(
            id="d-1",
            post_type="project",
            source_ref="project:p1",
            caption="hi",
            hashtags="#A",
            image_url="http://img",
            image_credit="cred",
            status=status,
        ),
    )
    if status != "pending":
        conn.execute("UPDATE drafts SET status = ? WHERE id = ?", (status, "d-1"))
        conn.commit()
    conn.close()
    return "d-1"


def test_next_scheduled_at_utc_picks_next_11am_et() -> None:
    nyc = ZoneInfo("America/New_York")
    now_local = datetime(2026, 5, 15, 9, 0, tzinfo=nyc)
    when = next_scheduled_at_utc(now_local, "America/New_York", time(11, 0))
    assert when.tzinfo is not None
    assert when.utcoffset().total_seconds() == 0
    # 11:00 EDT = 15:00 UTC (May is DST)
    assert when.hour == 15
    assert when.minute == 0


def test_next_scheduled_at_utc_rolls_over_after_11am() -> None:
    nyc = ZoneInfo("America/New_York")
    now_local = datetime(2026, 5, 15, 12, 0, tzinfo=nyc)
    when = next_scheduled_at_utc(now_local, "America/New_York", time(11, 0))
    assert when.day == 16


@freeze_time("2026-05-15T13:00:00Z")
def test_run_post_approve_schedules_buffer(settings: Settings) -> None:
    _seed_draft(settings.db_path)

    buffer_fn = MagicMock(return_value="upd123")
    email_fn = MagicMock()
    result = run_post(
        settings,
        draft_id="d-1",
        action="approve",
        buffer_schedule_fn=buffer_fn,
        email_send_fn=email_fn,
    )
    assert isinstance(result, PostResult)
    assert result.status == "posted"
    buffer_fn.assert_called_once()
    email_fn.assert_called_once()

    conn = init_db(settings.db_path)
    d = get_draft(conn, "d-1")
    conn.close()
    assert d is not None
    assert d.status == "posted"
    assert d.buffer_post_id == "upd123"


@freeze_time("2026-05-15T13:00:00Z")
def test_run_post_reject_marks_rejected(settings: Settings) -> None:
    _seed_draft(settings.db_path)

    buffer_fn = MagicMock()
    email_fn = MagicMock()
    result = run_post(
        settings,
        draft_id="d-1",
        action="reject",
        buffer_schedule_fn=buffer_fn,
        email_send_fn=email_fn,
    )
    assert result.status == "rejected"
    buffer_fn.assert_not_called()
    email_fn.assert_called_once()

    conn = init_db(settings.db_path)
    d = get_draft(conn, "d-1")
    conn.close()
    assert d is not None
    assert d.status == "rejected"


def test_run_post_idempotent_when_already_posted(settings: Settings) -> None:
    _seed_draft(settings.db_path, status="posted")
    buffer_fn = MagicMock()
    email_fn = MagicMock()
    result = run_post(
        settings,
        draft_id="d-1",
        action="approve",
        buffer_schedule_fn=buffer_fn,
        email_send_fn=email_fn,
    )
    assert result.status == "noop"
    buffer_fn.assert_not_called()


def test_run_post_unknown_draft_errors(settings: Settings) -> None:
    init_db(settings.db_path).close()
    buffer_fn = MagicMock()
    email_fn = MagicMock()
    result = run_post(
        settings,
        draft_id="missing",
        action="approve",
        buffer_schedule_fn=buffer_fn,
        email_send_fn=email_fn,
    )
    assert result.status == "error"
    buffer_fn.assert_not_called()
