from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from agent.db.store import (
    posted_project_ids,
    update_rotation_state,
)
from agent.profile_model import Profile, load_profile
from agent.rotation import (
    SUPPORTED_TYPES,
    WEEKLY_SCHEDULE,
    advance_after_draft,
    already_drafted_today,
    pick_today,
)


@pytest.fixture
def profile(sample_profile_path) -> Profile:
    return load_profile(sample_profile_path)


def test_pick_today_follows_weekly_schedule(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    # Mon 2026-05-11 → trending, Tue → concept, Wed → tutorial, Thu → roadmap,
    # Fri → news_take, Sat → career, Sun → project.
    expected = [
        (date(2026, 5, 11), "trending"),
        (date(2026, 5, 12), "concept"),
        (date(2026, 5, 13), "tutorial"),
        (date(2026, 5, 14), "roadmap"),
        (date(2026, 5, 15), "news_take"),
        (date(2026, 5, 16), "career"),
        (date(2026, 5, 17), "project"),
    ]
    for day, expected_type in expected:
        d = pick_today(tmp_db, profile, today=day)
        assert d is not None, f"no decision on {day}"
        assert d.post_type == expected_type, f"{day}: got {d.post_type}, want {expected_type}"


def test_pick_today_returns_none_if_already_drafted(
    tmp_db: sqlite3.Connection, profile: Profile
) -> None:
    update_rotation_state(tmp_db, last_day="2026-05-13")
    assert pick_today(tmp_db, profile, today=date(2026, 5, 13)) is None


def test_pick_today_force_overrides_last_day(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    update_rotation_state(tmp_db, last_day="2026-05-13")
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 13), force=True)
    assert decision is not None


def test_pick_today_with_explicit_post_type(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 13), override_post_type="project")
    assert decision is not None
    assert decision.post_type == "project"


def test_project_each_posted_only_once(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    """A given project should be selected at most once even across weeks."""
    chosen: list[str] = []
    # Force project type repeatedly; should walk through each project id and
    # then fall back to trending when the pool is empty.
    for _ in range(len(profile.projects)):
        d = pick_today(
            tmp_db,
            profile,
            today=date(2026, 5, 11),
            force=True,
            override_post_type="project",
        )
        assert d is not None
        assert d.post_type == "project"
        assert d.sub_key is not None
        assert d.sub_key not in chosen, "project repeated before pool exhausted"
        chosen.append(d.sub_key)
        advance_after_draft(tmp_db, d)

    assert set(chosen) == {p.id for p in profile.projects}
    # Pool exhausted; project Sunday falls back to trending automatically.
    fallback = pick_today(tmp_db, profile, today=date(2026, 5, 17), force=True)
    assert fallback is not None
    assert fallback.post_type == "trending"


def test_project_marked_posted_after_advance(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    d = pick_today(
        tmp_db,
        profile,
        today=date(2026, 5, 17),
        force=True,
        override_post_type="project",
    )
    assert d is not None and d.sub_key is not None
    advance_after_draft(tmp_db, d)
    assert d.sub_key in posted_project_ids(tmp_db)


def test_already_drafted_today(tmp_db: sqlite3.Connection) -> None:
    assert already_drafted_today(tmp_db, today=date(2026, 5, 13)) is False
    update_rotation_state(tmp_db, last_day="2026-05-13")
    assert already_drafted_today(tmp_db, today=date(2026, 5, 13)) is True


def test_weekly_schedule_constant() -> None:
    assert WEEKLY_SCHEDULE == (
        "trending",
        "concept",
        "tutorial",
        "roadmap",
        "news_take",
        "career",
        "project",
    )
    for t in WEEKLY_SCHEDULE:
        assert t in SUPPORTED_TYPES
