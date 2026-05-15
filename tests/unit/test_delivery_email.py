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


def test_build_draft_email_contains_caption_hashtags_image_and_buttons() -> None:
    msg = build_draft_email(
        draft=_sample_draft(),
        sender="a@b.com",
        recipient="a@b.com",
        approve_url="https://approval.example.workers.dev/a?t=APPTOKEN",
        reject_url="https://approval.example.workers.dev/r?t=REJTOKEN",
    )
    assert msg["Subject"].startswith("[LinkedIn Draft]")
    body_text = msg.get_body(preferencelist=("plain",)).get_content()
    body_html = msg.get_body(preferencelist=("html",)).get_content()
    assert "Hook line." in body_text
    assert "#DataScience" in body_text
    assert "APPROVE: https://approval.example.workers.dev/a?t=APPTOKEN" in body_text
    assert "REJECT: https://approval.example.workers.dev/r?t=REJTOKEN" in body_text
    assert "Hook line." in body_html
    assert 'href="https://approval.example.workers.dev/a?t=APPTOKEN"' in body_html
    assert 'href="https://approval.example.workers.dev/r?t=REJTOKEN"' in body_html
    assert "APPROVE" in body_html
    assert "REJECT" in body_html


def test_send_email_uses_smtp_client() -> None:
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = None
    msg = build_draft_email(
        draft=_sample_draft(),
        sender="a@b.com",
        recipient="a@b.com",
        approve_url="https://x/a",
        reject_url="https://x/r",
    )
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
