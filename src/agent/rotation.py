"""Decide today's post type and sub-key from rotation state + calendar."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from agent.db.store import RotationState, get_rotation_state, update_rotation_state
from agent.profile_model import Profile

PHASE1_TYPES: tuple[str, ...] = ("project", "concept", "tip")


@dataclass(frozen=True)
class RotationDecision:
    """What to post today and the rotating sub-selector inside that type."""

    post_type: str
    sub_key: str | None


def already_drafted_today(conn: sqlite3.Connection, today: date) -> bool:
    state = get_rotation_state(conn)
    return state.last_day == today.isoformat()


def _weekday_to_type(d: date) -> str:
    # Mon=0 → project, Tue=1 → concept, Wed=2 → tip, then cycle.
    return PHASE1_TYPES[d.weekday() % len(PHASE1_TYPES)]


def _skill_categories(profile: Profile) -> list[str]:
    return list(profile.skills.keys())


def _sub_key(post_type: str, profile: Profile, state: RotationState) -> str | None:
    if post_type == "project":
        if not profile.projects:
            return None
        idx = state.project_index % len(profile.projects)
        return profile.projects[idx].id
    if post_type == "concept":
        cats = _skill_categories(profile)
        if not cats:
            return None
        idx = state.skill_index % len(cats)
        return cats[idx]
    if post_type == "tip":
        if not profile.experience:
            return None
        idx = state.exp_index % len(profile.experience)
        return profile.experience[idx].id
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
    if post_type not in PHASE1_TYPES:
        raise ValueError(f"Unsupported post_type for phase 1: {post_type}")
    state = get_rotation_state(conn)
    return RotationDecision(post_type=post_type, sub_key=_sub_key(post_type, profile, state))


def advance_after_draft(conn: sqlite3.Connection, decision: RotationDecision) -> None:
    state = get_rotation_state(conn)
    if decision.post_type == "project":
        update_rotation_state(conn, project_index=state.project_index + 1)
    elif decision.post_type == "concept":
        update_rotation_state(conn, skill_index=state.skill_index + 1)
    elif decision.post_type == "tip":
        update_rotation_state(conn, exp_index=state.exp_index + 1)
