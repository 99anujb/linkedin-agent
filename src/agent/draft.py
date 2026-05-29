"""Draft pipeline entrypoint: pick → source → caption → hashtags → image → email."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from agent.auth.tokens import sign_token
from agent.config import Settings
from agent.db.store import (
    Draft,
    expire_stale_drafts,
    init_db,
    insert_draft,
    update_rotation_state,
)
from agent.delivery.email import build_draft_email, send_email
from agent.delivery.git_publish import commit_and_push
from agent.generators.caption import generate_caption
from agent.generators.hashtags import format_hashtags, generate_hashtags
from agent.generators.image_picker import pick_image
from agent.generators.snippet import generate_snippet
from agent.profile_model import load_profile
from agent.rotation import advance_after_draft, pick_today
from agent.sources.profile import build_source

log = logging.getLogger(__name__)


EmailSendFn = Callable[..., None]


@dataclass(frozen=True)
class DraftResult:
    status: str  # "drafted" | "skipped" | "dry_run" | "error"
    post_type: str | None = None
    draft_id: str | None = None
    message: str = ""


def _default_email_send(msg: EmailMessage, *, username: str, password: str) -> None:
    send_email(msg, username=username, password=password)


def run_draft(
    settings: Settings,
    *,
    anthropic_client: Any,
    image_fn: Any | None = None,  # deprecated, accepted for backwards-compat
    email_send_fn: EmailSendFn | None = None,
    today: date | None = None,
    force: bool = False,
    override_post_type: str | None = None,
    dry_run: bool = False,
) -> DraftResult:
    """Run the draft pipeline. `image_fn` is no longer consulted; image
    selection now lives in `agent.generators.image_picker`. The parameter
    is preserved so existing callers / tests continue to work."""
    _ = image_fn  # intentionally unused
    today = today or date.today()
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

        source = build_source(decision, profile, conn=conn)
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

        hook = "\n".join(caption.strip().splitlines()[:2])
        snippet_text: str | None = None
        snippet_language: str | None = None
        if decision.post_type in ("project", "tutorial"):
            try:
                snippet_text, snippet_language = generate_snippet(
                    anthropic_client,
                    caption=caption,
                    post_type=decision.post_type,
                )
            except Exception as exc:
                log.warning("snippet generation failed: %s", exc)

        draft_id = str(uuid.uuid4())
        image_path = Path("db/images") / f"{draft_id}.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)

        outcome = pick_image(
            post_type=decision.post_type,
            hook=hook,
            keywords=source.keywords,
            snippet=snippet_text,
            language=snippet_language,
            gemini_api_key=settings.gemini_api_key or None,
            unsplash_access_key=settings.unsplash_access_key or None,
        )
        if outcome.bytes_ is not None:
            image_path.write_bytes(outcome.bytes_)
            try:
                commit_and_push(
                    [image_path],
                    message=f"chore(image): {outcome.strategy} card for draft {draft_id}",
                )
            except Exception as exc:
                log.warning("git_publish failed: %s", exc)
            raw_base = settings.github_raw_base.rstrip("/")
            image_url = f"{raw_base}/db/images/{draft_id}.png"
            image_credit = outcome.credit
        else:
            image_url = outcome.url or ""
            image_credit = outcome.credit

        draft = Draft(
            id=draft_id,
            post_type=decision.post_type,
            source_ref=source.source_ref,
            caption=caption,
            hashtags=format_hashtags(tags),
            image_url=image_url,
            image_credit=image_credit,
        )

        if dry_run:
            log.info("DRY RUN — caption:\n%s\nhashtags: %s", caption, draft.hashtags)
            return DraftResult(status="dry_run", post_type=decision.post_type, draft_id=draft.id)

        insert_draft(conn, draft)
        advance_after_draft(conn, decision)
        update_rotation_state(conn, last_day=today.isoformat())

        approve_tok = sign_token(
            draft.id, "approve", ttl_seconds=24 * 3600, secret=settings.hmac_secret
        )
        reject_tok = sign_token(
            draft.id, "reject", ttl_seconds=24 * 3600, secret=settings.hmac_secret
        )
        base = settings.approval_base_url.rstrip("/")
        approve_url = f"{base}/a?t={approve_tok}"
        reject_url = f"{base}/r?t={reject_tok}"

        msg = build_draft_email(
            draft=draft,
            sender=settings.gmail_username,
            recipient=settings.gmail_recipient,
            approve_url=approve_url,
            reject_url=reject_url,
        )
        email_send_fn(msg)

        return DraftResult(status="drafted", post_type=decision.post_type, draft_id=draft.id)
    finally:
        conn.close()
