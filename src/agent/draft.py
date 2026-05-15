"""Draft pipeline entrypoint: pick → source → caption → hashtags → image → email."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from typing import Any

from agent.config import Settings
from agent.db.store import (
    Draft,
    expire_stale_drafts,
    init_db,
    insert_draft,
    update_rotation_state,
)
from agent.delivery.email import build_draft_email, send_email
from agent.generators.caption import generate_caption
from agent.generators.hashtags import format_hashtags, generate_hashtags
from agent.generators.image import ImageResult, fetch_image
from agent.profile_model import load_profile
from agent.rotation import advance_after_draft, pick_today
from agent.sources.profile import build_source

log = logging.getLogger(__name__)


ImageFn = Callable[..., ImageResult]
EmailSendFn = Callable[..., None]


@dataclass(frozen=True)
class DraftResult:
    status: str  # "drafted" | "skipped" | "dry_run" | "error"
    post_type: str | None = None
    draft_id: str | None = None
    message: str = ""


def _default_image_fn(keywords: list[str], access_key: str) -> ImageResult:
    return fetch_image(keywords=keywords, access_key=access_key)


def _default_email_send(msg: EmailMessage, *, username: str, password: str) -> None:
    send_email(msg, username=username, password=password)


def run_draft(
    settings: Settings,
    *,
    anthropic_client: Any,
    image_fn: ImageFn | None = None,
    email_send_fn: EmailSendFn | None = None,
    today: date | None = None,
    force: bool = False,
    override_post_type: str | None = None,
    dry_run: bool = False,
) -> DraftResult:
    today = today or date.today()
    image_fn = image_fn or (
        lambda keywords, **_: _default_image_fn(keywords, settings.unsplash_access_key)
    )
    email_send_fn = email_send_fn or (
        lambda msg, **_: _default_email_send(
            msg, username=settings.gmail_username, password=settings.gmail_app_password
        )
    )

    profile = load_profile(settings.profile_path)
    conn = init_db(settings.db_path)

    try:
        expire_stale_drafts(conn)
        decision = pick_today(
            conn,
            profile,
            today=today,
            force=force,
            override_post_type=override_post_type,
        )
        if decision is None:
            log.info("Already drafted today (%s); skipping.", today)
            return DraftResult(status="skipped", message=f"already drafted on {today}")

        source = build_source(decision, profile)
        caption = generate_caption(
            anthropic_client,
            post_type=decision.post_type,
            source=source,
            role_targets=profile.role_targets,
        )
        tags = generate_hashtags(
            anthropic_client,
            post_type=decision.post_type,
            caption=caption,
            keywords=source.keywords,
        )
        image = image_fn(keywords=source.keywords, access_key=settings.unsplash_access_key)

        draft = Draft(
            id=str(uuid.uuid4()),
            post_type=decision.post_type,
            source_ref=source.source_ref,
            caption=caption,
            hashtags=format_hashtags(tags),
            image_url=image.url,
            image_credit=image.credit,
        )

        if dry_run:
            log.info("DRY RUN — caption:\n%s\nhashtags: %s", caption, draft.hashtags)
            return DraftResult(status="dry_run", post_type=decision.post_type, draft_id=draft.id)

        insert_draft(conn, draft)
        advance_after_draft(conn, decision)
        update_rotation_state(conn, last_day=today.isoformat())

        msg = build_draft_email(
            draft=draft,
            sender=settings.gmail_username,
            recipient=settings.gmail_recipient,
            approve_url="https://placeholder/approve",  # TEMP — Task 5 wires real tokens
            reject_url="https://placeholder/reject",     # TEMP — Task 5 wires real tokens
        )
        email_send_fn(msg)

        return DraftResult(status="drafted", post_type=decision.post_type, draft_id=draft.id)
    finally:
        conn.close()
