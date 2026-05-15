from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from agent.db.store import (
    update_rotation_state,
)
from agent.profile_model import Profile, load_profile
from agent.rotation import (
    PHASE1_TYPES,
    advance_after_draft,
    already_drafted_today,
    pick_today,
)


@pytest.fixture
def profile(sample_profile_path) -> Profile:
    return load_profile(sample_profile_path)


def test_pick_today_cycles_through_types(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    # Mon 2026-05-11 → project
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 11))
    assert decision is not None
    assert decision.post_type == "project"

    # Tue → concept
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 12))
    assert decision is not None
    assert decision.post_type == "concept"

    # Wed → tip
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 13))
    assert decision is not None
    assert decision.post_type == "tip"

    # Thu → project again (3-day cycle in phase 1)
    decision = pick_today(tmp_db, profile, today=date(2026, 5, 14))
    assert decision is not None
    assert decision.post_type == "project"


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


def test_project_index_cycles(tmp_db: sqlite3.Connection, profile: Profile) -> None:
    # sample profile has 2 projects (p1, p2)
    d1 = pick_today(tmp_db, profile, today=date(2026, 5, 11))
    assert d1 is not None
    assert d1.sub_key == "p1"

    advance_after_draft(tmp_db, d1)
    update_rotation_state(tmp_db, last_day="2026-05-11")

    # Next project day → p2
    d2 = pick_today(tmp_db, profile, today=date(2026, 5, 14))
    assert d2 is not None
    assert d2.sub_key == "p2"

    advance_after_draft(tmp_db, d2)
    update_rotation_state(tmp_db, last_day="2026-05-14")

    # Wraps back to p1
    d3 = pick_today(tmp_db, profile, today=date(2026, 5, 17))
    assert d3 is not None
    assert d3.sub_key == "p1"


def test_already_drafted_today(tmp_db: sqlite3.Connection) -> None:
    assert already_drafted_today(tmp_db, today=date(2026, 5, 13)) is False
    update_rotation_state(tmp_db, last_day="2026-05-13")
    assert already_drafted_today(tmp_db, today=date(2026, 5, 13)) is True


def test_phase1_types_constant() -> None:
    assert PHASE1_TYPES == ("project", "concept", "tip")
