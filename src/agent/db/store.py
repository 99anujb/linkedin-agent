"""SQLite CRUD wrappers for drafts, rotation state, and history."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

DRAFT_TTL = timedelta(hours=24)


@dataclass
class Draft:
    id: str
    post_type: str
    caption: str
    hashtags: str
    source_ref: str | None = None
    image_url: str | None = None
    image_credit: str | None = None
    status: str = "pending"
    created_at: str = ""
    expires_at: str = ""
    approved_at: str | None = None
    posted_at: str | None = None
    buffer_post_id: str | None = None
    error: str | None = None


@dataclass
class RotationState:
    last_day: str | None
    project_index: int
    skill_index: int
    exp_index: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def init_db(path: Path) -> sqlite3.Connection:
    """Open (or create) the SQLite DB at `path` and apply schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    schema = (resources.files("agent.db") / "schema.sql").read_text()
    conn.executescript(schema)
    conn.commit()
    return conn


def insert_draft(conn: sqlite3.Connection, draft: Draft) -> None:
    now = _utcnow()
    expires = now + DRAFT_TTL
    conn.execute(
        """
        INSERT INTO drafts (
            id, created_at, post_type, source_ref, caption, hashtags,
            image_url, image_credit, status, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            draft.id,
            _iso(now),
            draft.post_type,
            draft.source_ref,
            draft.caption,
            draft.hashtags,
            draft.image_url,
            draft.image_credit,
            draft.status,
            _iso(expires),
        ),
    )
    conn.commit()


_DRAFT_COLS = (
    "id, created_at, post_type, source_ref, caption, hashtags, "
    "image_url, image_credit, status, expires_at, approved_at, posted_at, buffer_post_id, error"
)


def _row_to_draft(row: sqlite3.Row) -> Draft:
    return Draft(
        id=row["id"],
        created_at=row["created_at"],
        post_type=row["post_type"],
        source_ref=row["source_ref"],
        caption=row["caption"],
        hashtags=row["hashtags"],
        image_url=row["image_url"],
        image_credit=row["image_credit"],
        status=row["status"],
        expires_at=row["expires_at"],
        approved_at=row["approved_at"],
        posted_at=row["posted_at"],
        buffer_post_id=row["buffer_post_id"],
        error=row["error"],
    )


def get_draft(conn: sqlite3.Connection, draft_id: str) -> Draft | None:
    row = conn.execute(
        f"SELECT {_DRAFT_COLS} FROM drafts WHERE id = ?", (draft_id,)
    ).fetchone()
    return _row_to_draft(row) if row else None


def update_draft_status(
    conn: sqlite3.Connection,
    draft_id: str,
    status: str,
    *,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE drafts SET status = ?, error = COALESCE(?, error) WHERE id = ?",
        (status, error, draft_id),
    )
    conn.commit()


def list_pending(conn: sqlite3.Connection) -> list[Draft]:
    rows = conn.execute(
        f"SELECT {_DRAFT_COLS} FROM drafts WHERE status = 'pending' ORDER BY created_at"
    ).fetchall()
    return [_row_to_draft(r) for r in rows]


def expire_stale_drafts(conn: sqlite3.Connection) -> int:
    now = _iso(_utcnow())
    cur = conn.execute(
        "UPDATE drafts SET status = 'expired' WHERE status = 'pending' AND expires_at <= ?",
        (now,),
    )
    conn.commit()
    return cur.rowcount


def get_rotation_state(conn: sqlite3.Connection) -> RotationState:
    cur = conn.execute(
        "SELECT last_day, project_index, skill_index, exp_index FROM rotation_state WHERE id = 1"
    )
    cur.row_factory = sqlite3.Row
    row = cur.fetchone()
    return RotationState(
        last_day=row["last_day"],
        project_index=row["project_index"],
        skill_index=row["skill_index"],
        exp_index=row["exp_index"],
    )


def update_rotation_state(
    conn: sqlite3.Connection,
    *,
    last_day: str | None = None,
    project_index: int | None = None,
    skill_index: int | None = None,
    exp_index: int | None = None,
) -> None:
    current = get_rotation_state(conn)
    conn.execute(
        """
        UPDATE rotation_state SET
            last_day = ?, project_index = ?, skill_index = ?, exp_index = ?
        WHERE id = 1
        """,
        (
            last_day if last_day is not None else current.last_day,
            project_index if project_index is not None else current.project_index,
            skill_index if skill_index is not None else current.skill_index,
            exp_index if exp_index is not None else current.exp_index,
        ),
    )
    conn.commit()
