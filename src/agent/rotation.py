"""Decide today's post type and sub-key from rotation state + calendar."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from agent.db.store import (
    RotationState,
    get_rotation_state,
    posted_project_ids,
    record_posted_project,
    update_rotation_state,
)
from agent.profile_model import Profile

# Weekly schedule (Mon=0 ... Sun=6). Projects only on Sunday and only when
# there is at least one unposted project; otherwise Sunday falls back to
# trending so the agent never re-posts the same project.
WEEKLY_SCHEDULE: tuple[str, ...] = (
    "trending",  # Mon
    "concept",  # Tue
    "tutorial",  # Wed
    "roadmap",  # Thu
    "news_take",  # Fri
    "career",  # Sat
    "project",  # Sun (falls back to trending if no unposted projects)
)

SUPPORTED_TYPES: tuple[str, ...] = (
    "project",
    "concept",
    "career",
    "trending",
    "tutorial",
    "roadmap",
    "news_take",
)


@dataclass(frozen=True)
class RotationDecision:
    """What to post today and the rotating sub-selector inside that type."""

    post_type: str
    sub_key: str | None


def already_drafted_today(conn: sqlite3.Connection, today: date) -> bool:
    state = get_rotation_state(conn)
    return state.last_day == today.isoformat()


def _weekday_to_type(d: date) -> str:
    return WEEKLY_SCHEDULE[d.weekday() % len(WEEKLY_SCHEDULE)]


def _skill_categories(profile: Profile) -> list[str]:
    return list(profile.skills.keys())


def _unposted_projects(profile: Profile, conn: sqlite3.Connection) -> list[str]:
    """Return ids of profile projects that have NOT been posted yet."""
    posted = posted_project_ids(conn)
    return [p.id for p in profile.projects if p.id not in posted]


def _next_unposted_project_id(
    profile: Profile, conn: sqlite3.Connection, state: RotationState
) -> str | None:
    """Round-robin through unposted projects; return None if all are posted."""
    pending = _unposted_projects(profile, conn)
    if not pending:
        return None
    idx = state.project_index % len(pending)
    return pending[idx]


def _sub_key(
    post_type: str, profile: Profile, conn: sqlite3.Connection, state: RotationState
) -> str | None:
    if post_type == "project":
        return _next_unposted_project_id(profile, conn, state)
    if post_type == "concept":
        cats = _skill_categories(profile)
        if not cats:
            return None
        idx = state.skill_index % len(cats)
        return cats[idx]
    if post_type == "career":
        if not profile.achievements:
            return None
        idx = state.exp_index % len(profile.achievements)
        return f"achv_{idx}"
    if post_type == "tutorial":
        cats = _skill_categories(profile)
        if not cats:
            return None
        idx = state.skill_index % len(cats)
        return cats[idx]
    if post_type == "roadmap":
        targets = profile.role_targets or ["Data Scientist"]
        idx = state.exp_index % len(targets)
        return targets[idx]
    # trending and news_take get their sub_key from the RSS layer (the
    # chosen headline). Leave as None here; the source builder fills it in.
    return None


def pick_today(
    conn: sqlite3.Connection,
    profile: Profile,
    *,
    today: date,
    force: bool = False,
    override_post_type: str | None = None,
) -> RotationDecision | None:
    """Return today's draft decision, or None if already drafted (and not forced)."""
    if not force and already_drafted_today(conn, today):
        return None
    post_type = override_post_type or _weekday_to_type(today)
    if post_type not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported post_type: {post_type}")
    state = get_rotation_state(conn)

    # Project Sundays fall back to trending when the project pool is empty.
    if post_type == "project" and not _unposted_projects(profile, conn):
        post_type = "trending"

    return RotationDecision(
        post_type=post_type,
        sub_key=_sub_key(post_type, profile, conn, state),
    )


def advance_after_draft(conn: sqlite3.Connection, decision: RotationDecision) -> None:
    state = get_rotation_state(conn)
    if decision.post_type == "project":
        update_rotation_state(conn, project_index=state.project_index + 1)
        if decision.sub_key:
            record_posted_project(conn, decision.sub_key)
    elif decision.post_type in ("concept", "tutorial"):
        update_rotation_state(conn, skill_index=state.skill_index + 1)
    elif decision.post_type in ("career", "roadmap"):
        update_rotation_state(conn, exp_index=state.exp_index + 1)
    # trending and news_take do not advance any rotation counter.
