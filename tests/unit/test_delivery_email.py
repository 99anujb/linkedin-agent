from __future__ import annotations

from unittest.mock import MagicMock

from agent.db.store import Draft
from agent.delivery.email import build_draft_email, send_email


def _sample_draft() -> Draft:
    return Draft(
        id="d-test",
        post_type="project",
        source_ref="project:afm",
        caption="Hook line.\n\nBody paragraph one.\n\nQuestion?",
        hashtags="#DataScience #DeepLearning #PyTorch",
        image_url="https://images.unsplash.com/x",
        image_credit="Photo by Jane on Unsplash",
        status="pending",
        created_at="2026-05-13T12:00:00+00:00",
        expires_at="2026-05-14T12:00:00+00:00",
    )


def test_build_draft_email_contains_caption_hashtags_image() -> None:
    msg = build_draft_email(
        draft=_sample_draft(),
        sender="a@b.com",
        recipient="a@b.com",
    )
    assert msg["Subject"].startswith("[LinkedIn Draft]")
    assert msg["From"] == "a@b.com"
    assert msg["To"] == "a@b.com"
    body_text = msg.get_body(preferencelist=("plain",)).get_content()
    body_html = msg.get_body(preferencelist=("html",)).get_content()
    assert "Hook line." in body_text
    assert "#DataScience" in body_text
    assert "Hook line." in body_html
    assert "https://images.unsplash.com/x" in body_html
    assert "Photo by Jane" in body_html


def test_send_email_uses_smtp_client() -> None:
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = None
    msg = build_draft_email(draft=_sample_draft(), sender="a@b.com", recipient="a@b.com")

    send_email(
        msg,
        host="smtp.gmail.com",
        port=465,
        username="a@b.com",
        password="pw",
        smtp_factory=lambda host, port: smtp,
    )

    smtp.login.assert_called_once_with("a@b.com", "pw")
    smtp.send_message.assert_called_once()
    sent_msg = smtp.send_message.call_args[0][0]
    assert sent_msg["Subject"].startswith("[LinkedIn Draft]")
