"""Build and send the draft preview email via Gmail SMTP."""

from __future__ import annotations

import logging
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

from agent.db.store import Draft

log = logging.getLogger(__name__)


def _subject(draft: Draft) -> str:
    first_line = draft.caption.splitlines()[0] if draft.caption else "(empty)"
    return f"[LinkedIn Draft] {first_line[:60]}"


def _plain_body(draft: Draft, approve_url: str, reject_url: str) -> str:
    return (
        f"Post type: {draft.post_type}\n"
        f"Source: {draft.source_ref}\n"
        f"Draft ID: {draft.id}\n"
        f"Expires: {draft.expires_at}\n"
        f"\n"
        f"APPROVE: {approve_url}\n"
        f"REJECT: {reject_url}\n"
        f"\n"
        f"--- CAPTION ---\n"
        f"{draft.caption}\n"
        f"\n"
        f"--- HASHTAGS ---\n"
        f"{draft.hashtags}\n"
        f"\n"
        f"--- IMAGE ---\n"
        f"{draft.image_url or '(none)'}\n"
        f"{draft.image_credit or ''}\n"
    )


def _button(href: str, label: str, color: str) -> str:
    return (
        f'<a href="{href}" '
        f'style="display:inline-block;padding:12px 24px;margin:0 8px 0 0;'
        f"background:{color};color:#fff;font-weight:600;text-decoration:none;"
        f'border-radius:6px;font-family:-apple-system,Segoe UI,Roboto,sans-serif">'
        f"{label}</a>"
    )


def _html_body(draft: Draft, approve_url: str, reject_url: str) -> str:
    image_html = (
        f'<p><img src="{draft.image_url}" alt="suggested image" '
        f'style="max-width:520px;border:1px solid #ddd;border-radius:6px"/></p>'
        f'<p style="color:#666;font-size:12px">{draft.image_credit or ""}</p>'
        if draft.image_url
        else ""
    )
    caption_html = draft.caption.replace("\n\n", "</p><p>").replace("\n", "<br/>")
    approve_btn = _button(approve_url, "APPROVE", "#0a66c2")
    reject_btn = _button(reject_url, "REJECT", "#6b7280")
    return f"""\
<html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5">
  <h2 style="margin:0 0 4px 0">LinkedIn Draft - {draft.post_type}</h2>
  <p style="color:#888;margin:0 0 16px 0;font-size:13px">
    Source: {draft.source_ref or '-'} | Draft ID: {draft.id} | Expires: {draft.expires_at}
  </p>
  {image_html}
  <div style="background:#f7f7f9;padding:16px;border-radius:8px;margin:16px 0">
    <p>{caption_html}</p>
  </div>
  <p style="font-weight:600">Hashtags</p>
  <p style="color:#0a66c2">{draft.hashtags}</p>
  <div style="margin:24px 0">{approve_btn}{reject_btn}</div>
  <hr/>
  <p style="color:#888;font-size:12px">
    Click APPROVE to schedule on Buffer at the configured local time. Token expires in 24h.
  </p>
</body></html>
"""


def build_draft_email(
    *,
    draft: Draft,
    sender: str,
    recipient: str,
    approve_url: str,
    reject_url: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = _subject(draft)
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(_plain_body(draft, approve_url, reject_url))
    msg.add_alternative(_html_body(draft, approve_url, reject_url), subtype="html")
    return msg


SmtpFactory = Callable[[str, int], Any]


def _default_smtp_factory(host: str, port: int) -> smtplib.SMTP_SSL:
    return smtplib.SMTP_SSL(host, port, context=ssl.create_default_context())


def send_email(
    msg: EmailMessage,
    *,
    host: str = "smtp.gmail.com",
    port: int = 465,
    username: str,
    password: str,
    smtp_factory: SmtpFactory = _default_smtp_factory,
) -> None:
    log.info("Sending email to %s via %s:%s", msg["To"], host, port)
    with smtp_factory(host, port) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)
