"""Post pipeline entrypoint: approve schedules on Buffer; reject marks draft."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from agent.config import Settings
from agent.db.store import get_draft, init_db, update_draft_status
from agent.delivery.buffer import schedule_update
from agent.delivery.email import send_email

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostResult:
    status: str  # "posted" | "rejected" | "noop" | "error"
    draft_id: str
    message: str = ""
    buffer_post_id: str | None = None


BufferScheduleFn = Callable[..., str]
EmailSendFn = Callable[[EmailMessage], None]


def next_scheduled_at_utc(now_local: datetime, tz_name: str, target: time) -> datetime:
    """Return the next datetime (in UTC) that matches `target` in `tz_name`.

    If `now_local` is past today's target, returns tomorrow.
    """
    tz = ZoneInfo(tz_name)
    if now_local.tzinfo is None:
        now_local = now_local.replace(tzinfo=tz)
    today_target = datetime.combine(now_local.date(), target, tzinfo=tz)
    if now_local >= today_target:
        today_target = today_target + timedelta(days=1)
    return today_target.astimezone(ZoneInfo("UTC"))


def _confirmation_message(
    *, sender: str, recipient: str, draft_id: str, action: str, detail: str
) -> EmailMessage:
    m = EmailMessage()
    m["Subject"] = f"[LinkedIn] {action} - {draft_id}"
    m["From"] = sender
    m["To"] = recipient
    m.set_content(f"Action: {action}\nDraft: {draft_id}\nDetail: {detail}\n")
    return m


def run_post(
    settings: Settings,
    *,
    draft_id: str,
    action: str,
    buffer_schedule_fn: BufferScheduleFn | None = None,
    email_send_fn: EmailSendFn | None = None,
) -> PostResult:
    """Approve = schedule on Buffer. Reject = mark rejected. Both = email confirm."""
    if action not in ("approve", "reject"):
        return PostResult(status="error", draft_id=draft_id, message=f"bad action: {action}")

    bsf: BufferScheduleFn = buffer_schedule_fn or (lambda **kwargs: schedule_update(**kwargs))
    esf: EmailSendFn = email_send_fn or (
        lambda msg: send_email(
            msg,
            username=settings.gmail_username,
            password=settings.gmail_app_password,
        )
    )

    conn = init_db(settings.db_path)
    try:
        draft = get_draft(conn, draft_id)
        if draft is None:
            return PostResult(status="error", draft_id=draft_id, message="draft not found")
        if draft.status not in ("pending", "approved"):
            log.info("Draft %s already in status %s - no-op", draft_id, draft.status)
            return PostResult(status="noop", draft_id=draft_id, message=draft.status)

        if action == "reject":
            update_draft_status(conn, draft_id, "rejected")
            msg = _confirmation_message(
                sender=settings.gmail_username,
                recipient=settings.gmail_recipient,
                draft_id=draft_id,
                action="rejected",
                detail="Draft rejected; will retry next cron cycle.",
            )
            esf(msg)
            return PostResult(status="rejected", draft_id=draft_id)

        # action == "approve"
        hour, minute = (int(part) for part in settings.post_local_time.split(":", 1))
        target = time(hour=hour, minute=minute)
        now_local = datetime.now(ZoneInfo(settings.post_local_timezone))
        when = next_scheduled_at_utc(now_local, settings.post_local_timezone, target)

        post_text = f"{draft.caption}\n\n{draft.hashtags}"
        buffer_post_id = bsf(
            access_token=settings.buffer_access_token,
            profile_id=settings.buffer_linkedin_profile_id,
            text=post_text,
            media_link=draft.image_url,
            scheduled_at=when,
        )

        conn.execute(
            "UPDATE drafts SET status = 'posted', buffer_post_id = ?, posted_at = ? WHERE id = ?",
            (
                buffer_post_id,
                datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
                draft_id,
            ),
        )
        conn.execute(
            "INSERT INTO post_history (draft_id, post_type, source_ref, posted_at, linkedin_url) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                draft_id,
                draft.post_type,
                draft.source_ref,
                when.isoformat(timespec="seconds"),
                f"buffer:{buffer_post_id}",
            ),
        )
        conn.commit()

        msg = _confirmation_message(
            sender=settings.gmail_username,
            recipient=settings.gmail_recipient,
            draft_id=draft_id,
            action="scheduled",
            detail=f"Scheduled on Buffer for {when.isoformat()} UTC (buffer id {buffer_post_id}).",
        )
        esf(msg)
        return PostResult(status="posted", draft_id=draft_id, buffer_post_id=buffer_post_id)
    finally:
        conn.close()
