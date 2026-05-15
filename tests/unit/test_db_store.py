from __future__ import annotations

import sqlite3
from pathlib import Path

from freezegun import freeze_time

from agent.db.store import (
    Draft,
    RotationState,
    expire_stale_drafts,
    get_draft,
    get_rotation_state,
    init_db,
    insert_draft,
    list_pending,
    update_draft_status,
    update_rotation_state,
)


def test_init_db_creates_tables(tmp_db_path: Path) -> None:
    conn = init_db(tmp_db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    names = {row[0] for row in cur.fetchall()}
    assert {"drafts", "rotation_state", "post_history"}.issubset(names)
    # rotation_state seeded
    row = conn.execute("SELECT id, project_index FROM rotation_state").fetchone()
    assert row["id"] == 1
    assert row["project_index"] == 0
    conn.close()


def test_insert_and_get_draft(tmp_db: sqlite3.Connection) -> None:
    with freeze_time("2026-05-13T12:00:00Z"):
        draft = Draft(
            id="d1",
            post_type="project",
            source_ref="project:p1",
            caption="hi",
            hashtags="#a #b",
            image_url="http://img",
            image_credit="cred",
        )
        insert_draft(tmp_db, draft)

    got = get_draft(tmp_db, "d1")
    assert got is not None
    assert got.id == "d1"
    assert got.caption == "hi"
    assert got.status == "pending"
    assert got.created_at == "2026-05-13T12:00:00+00:00"
    assert got.expires_at == "2026-05-14T12:00:00+00:00"


def test_update_draft_status(tmp_db: sqlite3.Connection) -> None:
    insert_draft(
        tmp_db,
        Draft(
            id="d2",
            post_type="tip",
            source_ref=None,
            caption="x",
            hashtags="#x",
            image_url=None,
            image_credit=None,
        ),
    )
    update_draft_status(tmp_db, "d2", "rejected")
    got = get_draft(tmp_db, "d2")
    assert got is not None
    assert got.status == "rejected"


def test_list_pending_excludes_others(tmp_db: sqlite3.Connection) -> None:
    insert_draft(tmp_db, Draft(id="a", post_type="tip", caption="a", hashtags=""))
    insert_draft(tmp_db, Draft(id="b", post_type="tip", caption="b", hashtags=""))
    update_draft_status(tmp_db, "b", "rejected")
    pending = list_pending(tmp_db)
    assert [d.id for d in pending] == ["a"]


def test_expire_stale_drafts(tmp_db: sqlite3.Connection) -> None:
    with freeze_time("2026-05-13T12:00:00Z"):
        insert_draft(tmp_db, Draft(id="old", post_type="tip", caption="x", hashtags=""))
    with freeze_time("2026-05-14T13:00:00Z"):
        count = expire_stale_drafts(tmp_db)
    assert count == 1
    got = get_draft(tmp_db, "old")
    assert got is not None
    assert got.status == "expired"


def test_rotation_state_get_update(tmp_db: sqlite3.Connection) -> None:
    state = get_rotation_state(tmp_db)
    assert isinstance(state, RotationState)
    assert state.project_index == 0
    assert state.last_day is None

    update_rotation_state(tmp_db, last_day="2026-05-13", project_index=1)
    new_state = get_rotation_state(tmp_db)
    assert new_state.last_day == "2026-05-13"
    assert new_state.project_index == 1
    # unchanged fields preserved
    assert new_state.skill_index == 0
