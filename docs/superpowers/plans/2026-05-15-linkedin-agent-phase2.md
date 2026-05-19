# LinkedIn Auto-Post Agent — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Buffer-backed auto-scheduling and a Cloudflare Worker approval click-through, so a daily draft email contains APPROVE / REJECT links that, when clicked, trigger a GitHub Actions workflow which schedules the post on Buffer for 11:00 ET.

**Architecture:** A Cloudflare Worker (`worker/approval.js`) receives `GET /a?t=token` and `GET /r?t=token` requests, verifies an HMAC-signed token, and calls the GitHub REST API to `workflow_dispatch` a new `post.yml` workflow with `draft_id` and `action`. The workflow runs `python -m agent post`, which loads the draft from SQLite and (for approval) calls the Buffer API to schedule the post.

**Tech Stack:**
- New runtime: Cloudflare Workers (JavaScript + `wrangler` CLI)
- New deps: standard-library `hmac`, `hashlib`, `base64`, `time` (no new Python deps)
- Buffer Classic API (`https://api.bufferapp.com/1/...`) — works for personal accounts on free plan
- GitHub REST API — `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches`

**Scope boundaries (Phase 2):**
- Only adds the approve / reject click flow on top of Phase 1.
- Email still drafted by Phase 1 cron; this phase adds buttons + listener.
- Reject = mark draft `rejected` in DB; no further action.
- Approve = call Buffer API to schedule the post.
- One-time bootstrap: discover the Buffer LinkedIn profile ID via a CLI helper.
- DST handling: Buffer accepts ISO8601 UTC timestamps; compute next 11:00 ET in Python with `zoneinfo`.

---

## File Structure

Files this plan creates or modifies (paths relative to repo root):

```
linkedin-agent/
├── src/agent/
│   ├── auth/
│   │   ├── __init__.py                  # NEW: empty
│   │   └── tokens.py                    # NEW: HMAC sign/verify
│   ├── delivery/
│   │   └── buffer.py                    # NEW: Buffer API client
│   ├── post.py                          # NEW: approve/reject pipeline
│   ├── draft.py                         # MODIFY: produce signed tokens, pass to email
│   ├── delivery/email.py                # MODIFY: APPROVE/REJECT buttons in HTML
│   ├── __main__.py                      # MODIFY: add `post` subcommand
│   └── config.py                        # MODIFY: add new Settings fields
├── worker/
│   ├── approval.js                      # NEW: Cloudflare Worker source
│   ├── wrangler.toml                    # NEW: deploy config
│   └── README.md                        # NEW: deploy walkthrough
├── scripts/
│   └── discover_buffer_profile.py       # NEW: one-time CLI helper
├── tests/unit/
│   ├── test_auth_tokens.py              # NEW
│   ├── test_delivery_buffer.py          # NEW
│   ├── test_post_pipeline.py            # NEW
│   ├── test_delivery_email.py           # MODIFY: assert approve/reject links
│   └── test_draft_pipeline.py           # MODIFY: assert email got tokens
├── .github/workflows/
│   └── post.yml                         # NEW: workflow_dispatch on approval
├── .env.example                         # MODIFY: add new keys
├── README.md                            # MODIFY: Phase 2 deploy section
└── docs/superpowers/plans/2026-05-15-linkedin-agent-phase2.md (this file)
```

Module responsibilities:

| Module | Job | Depends on |
|---|---|---|
| `auth/tokens.py` | sign(draft_id, action, ttl) → b64 token; verify(token, secret) → (draft_id, action) or raises | stdlib hmac |
| `delivery/buffer.py` | list_profiles(token), schedule_update(profile_id, text, link, scheduled_at, token) | httpx |
| `post.py` | run_post(settings, draft_id, action) — load draft → buffer/mark → email confirm | db.store, delivery.buffer, delivery.email |
| `worker/approval.js` | HTTP handler: verify HMAC, dispatch GH workflow, return HTML | none (CF runtime) |
| `scripts/discover_buffer_profile.py` | One-time: call Buffer profiles API, print LinkedIn profile_id | delivery.buffer |

---

## Configuration additions

`Settings` (and `.env.example`) gain six new fields:

| Field | Purpose |
|---|---|
| `BUFFER_ACCESS_TOKEN` | Buffer API token from `https://publish.buffer.com/developers/apps` |
| `BUFFER_LINKEDIN_PROFILE_ID` | Profile id discovered via `scripts/discover_buffer_profile.py` |
| `HMAC_SECRET` | 32-byte random secret; signs approval tokens. `python -c "import secrets;print(secrets.token_urlsafe(32))"` |
| `APPROVAL_BASE_URL` | Public Worker URL, e.g. `https://approval.<your-name>.workers.dev` |
| `POST_LOCAL_TIMEZONE` | IANA tz, default `America/New_York`. Used to compute next 11:00 ET. |
| `POST_LOCAL_TIME` | `HH:MM` 24h, default `11:00`. |

`POST_LOCAL_TIMEZONE` and `POST_LOCAL_TIME` have defaults; the other four are required.

---

## Task 1: HMAC token module

**Files:**
- Create: `src/agent/auth/__init__.py`
- Create: `src/agent/auth/tokens.py`
- Test: `tests/unit/test_auth_tokens.py`

- [ ] **Step 1.1: Create package marker**

`src/agent/auth/__init__.py`: empty.

- [ ] **Step 1.2: Write the failing tests**

`tests/unit/test_auth_tokens.py`:

```python
from __future__ import annotations

import time

import pytest
from freezegun import freeze_time

from agent.auth.tokens import TokenError, sign_token, verify_token


SECRET = "test-secret-32-bytes-aaaaaaaaaaaaaaaa"


@freeze_time("2026-05-15T12:00:00Z")
def test_sign_verify_roundtrip() -> None:
    tok = sign_token("draft-123", "approve", ttl_seconds=3600, secret=SECRET)
    assert isinstance(tok, str) and len(tok) > 16
    draft_id, action = verify_token(tok, secret=SECRET)
    assert draft_id == "draft-123"
    assert action == "approve"


def test_tampered_token_rejected() -> None:
    tok = sign_token("d", "approve", ttl_seconds=3600, secret=SECRET)
    bad = tok[:-2] + ("AA" if tok[-2:] != "AA" else "BB")
    with pytest.raises(TokenError, match="signature"):
        verify_token(bad, secret=SECRET)


def test_wrong_secret_rejected() -> None:
    tok = sign_token("d", "approve", ttl_seconds=3600, secret=SECRET)
    with pytest.raises(TokenError, match="signature"):
        verify_token(tok, secret="other-secret-aaaaaaaaaaaaaaaaaaaaaaaa")


def test_expired_token_rejected() -> None:
    with freeze_time("2026-05-15T12:00:00Z"):
        tok = sign_token("d", "approve", ttl_seconds=60, secret=SECRET)
    with freeze_time("2026-05-15T12:01:01Z"):
        with pytest.raises(TokenError, match="expired"):
            verify_token(tok, secret=SECRET)


def test_invalid_action_rejected() -> None:
    with pytest.raises(ValueError, match="action"):
        sign_token("d", "explode", ttl_seconds=60, secret=SECRET)


def test_garbage_token_rejected() -> None:
    with pytest.raises(TokenError):
        verify_token("not-a-token", secret=SECRET)
```

- [ ] **Step 1.3: Verify failure**

```bash
pytest tests/unit/test_auth_tokens.py -v
```

Expected: ImportError on `agent.auth.tokens`.

- [ ] **Step 1.4: Implement `src/agent/auth/tokens.py`**

```python
"""HMAC-signed approval tokens for the LinkedIn agent."""

from __future__ import annotations

import base64
import hmac
import time
from hashlib import sha256

VALID_ACTIONS = ("approve", "reject")


class TokenError(Exception):
    """Raised when a token fails verification."""


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _payload(draft_id: str, action: str, expires_ts: int) -> bytes:
    return f"{draft_id}|{action}|{expires_ts}".encode()


def sign_token(draft_id: str, action: str, *, ttl_seconds: int, secret: str) -> str:
    if action not in VALID_ACTIONS:
        raise ValueError(f"invalid action: {action!r}")
    expires_ts = int(time.time()) + int(ttl_seconds)
    payload = _payload(draft_id, action, expires_ts)
    sig = hmac.new(secret.encode(), payload, sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(sig)}"


def verify_token(token: str, *, secret: str) -> tuple[str, str]:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64decode(payload_b64)
        sig = _b64decode(sig_b64)
    except (ValueError, base64.binascii.Error) as e:
        raise TokenError(f"malformed token: {e}") from e

    expected = hmac.new(secret.encode(), payload, sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise TokenError("bad signature")

    try:
        draft_id, action, expires_str = payload.decode().split("|", 2)
        expires_ts = int(expires_str)
    except (UnicodeDecodeError, ValueError) as e:
        raise TokenError(f"malformed payload: {e}") from e

    if int(time.time()) > expires_ts:
        raise TokenError("token expired")
    if action not in VALID_ACTIONS:
        raise TokenError(f"unknown action: {action}")
    return draft_id, action
```

- [ ] **Step 1.5: Run tests**

```bash
pytest tests/unit/test_auth_tokens.py -v
```

Expected: 6 passed.

- [ ] **Step 1.6: Commit**

```bash
git add src/agent/auth/ tests/unit/test_auth_tokens.py
git commit -m "feat(auth): HMAC-signed approval tokens with TTL"
```

---

## Task 2: Buffer API client

**Files:**
- Create: `src/agent/delivery/buffer.py`
- Test: `tests/unit/test_delivery_buffer.py`

- [ ] **Step 2.1: Write the failing tests**

`tests/unit/test_delivery_buffer.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from agent.delivery.buffer import (
    BufferError,
    BufferProfile,
    list_profiles,
    schedule_update,
)


@respx.mock
def test_list_profiles_returns_objects() -> None:
    respx.get("https://api.bufferapp.com/1/profiles.json").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "p1", "service": "linkedin", "service_username": "anuj"},
                {"id": "p2", "service": "twitter", "service_username": "anuj"},
            ],
        )
    )
    profiles = list_profiles(access_token="tkn")
    assert len(profiles) == 2
    assert profiles[0] == BufferProfile(id="p1", service="linkedin", username="anuj")


@respx.mock
def test_list_profiles_http_error_raises() -> None:
    respx.get("https://api.bufferapp.com/1/profiles.json").mock(
        return_value=httpx.Response(401, json={"error": "bad token"})
    )
    with pytest.raises(BufferError, match="401"):
        list_profiles(access_token="tkn")


@respx.mock
def test_schedule_update_posts_correct_payload() -> None:
    route = respx.post("https://api.bufferapp.com/1/updates/create.json").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "updates": [{"id": "u123"}]},
        )
    )
    when = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    update_id = schedule_update(
        access_token="tkn",
        profile_id="p1",
        text="hello\n\n#A #B",
        media_link="https://images.example/x.jpg",
        scheduled_at=when,
    )
    assert update_id == "u123"
    sent = route.calls.last.request
    assert b"profile_ids%5B%5D=p1" in sent.content
    assert b"scheduled_at=1747407600" in sent.content
    assert b"hello" in sent.content
    assert b"media%5Blink%5D=https%3A%2F%2Fimages.example%2Fx.jpg" in sent.content


@respx.mock
def test_schedule_update_buffer_error_raises() -> None:
    respx.post("https://api.bufferapp.com/1/updates/create.json").mock(
        return_value=httpx.Response(403, json={"error": "rate limited"})
    )
    when = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    with pytest.raises(BufferError, match="403"):
        schedule_update(
            access_token="tkn",
            profile_id="p1",
            text="x",
            media_link=None,
            scheduled_at=when,
        )
```

- [ ] **Step 2.2: Verify failure**

```bash
pytest tests/unit/test_delivery_buffer.py -v
```

Expected: ImportError.

- [ ] **Step 2.3: Implement `src/agent/delivery/buffer.py`**

```python
"""Minimal Buffer Classic API client (free-plan compatible)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

BUFFER_BASE = "https://api.bufferapp.com/1"
log = logging.getLogger(__name__)


class BufferError(Exception):
    """Buffer API returned a non-2xx status or malformed body."""


@dataclass(frozen=True)
class BufferProfile:
    id: str
    service: str
    username: str


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def list_profiles(*, access_token: str) -> list[BufferProfile]:
    """Return all channels connected to the Buffer account."""
    url = f"{BUFFER_BASE}/profiles.json"
    log.info("Listing Buffer profiles")
    resp = httpx.get(url, headers=_auth_headers(access_token), timeout=15.0)
    if resp.status_code != 200:
        raise BufferError(f"profiles.json returned {resp.status_code}: {resp.text}")
    data = resp.json()
    return [
        BufferProfile(
            id=item["id"],
            service=item.get("service", ""),
            username=item.get("service_username", ""),
        )
        for item in data
    ]


def schedule_update(
    *,
    access_token: str,
    profile_id: str,
    text: str,
    media_link: str | None,
    scheduled_at: datetime,
) -> str:
    """Schedule a single post on Buffer. Returns the update_id."""
    url = f"{BUFFER_BASE}/updates/create.json"
    data: list[tuple[str, str]] = [
        ("profile_ids[]", profile_id),
        ("text", text),
        ("scheduled_at", str(int(scheduled_at.timestamp()))),
    ]
    if media_link:
        data.append(("media[link]", media_link))
    log.info(
        "Scheduling Buffer update for %s at %s (UTC ts=%s)",
        profile_id,
        scheduled_at.isoformat(),
        int(scheduled_at.timestamp()),
    )
    resp = httpx.post(url, headers=_auth_headers(access_token), data=data, timeout=15.0)
    if resp.status_code != 200:
        raise BufferError(f"updates/create.json returned {resp.status_code}: {resp.text}")
    body = resp.json()
    if not body.get("success"):
        raise BufferError(f"updates/create.json not successful: {body}")
    updates = body.get("updates") or []
    if not updates:
        raise BufferError(f"no updates returned: {body}")
    return updates[0]["id"]
```

- [ ] **Step 2.4: Run tests**

```bash
pytest tests/unit/test_delivery_buffer.py -v
```

Expected: 4 passed.

- [ ] **Step 2.5: Commit**

```bash
git add src/agent/delivery/buffer.py tests/unit/test_delivery_buffer.py
git commit -m "feat(buffer): Buffer Classic API client (profiles + schedule_update)"
```

---

## Task 3: Extend Settings with Phase 2 fields

**Files:**
- Modify: `src/agent/config.py`
- Modify: `.env.example`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 3.1: Update tests**

Append to `tests/unit/test_config.py`:

```python
def test_settings_includes_phase2_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _full_env()
    env.update(
        {
            "BUFFER_ACCESS_TOKEN": "btoken",
            "BUFFER_LINKEDIN_PROFILE_ID": "p1",
            "HMAC_SECRET": "secret-32-bytes-aaaaaaaaaaaaaaaa",
            "APPROVAL_BASE_URL": "https://approval.example.workers.dev",
            "POST_LOCAL_TIMEZONE": "America/New_York",
            "POST_LOCAL_TIME": "11:00",
        }
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    s = load_settings()
    assert s.buffer_access_token == "btoken"
    assert s.buffer_linkedin_profile_id == "p1"
    assert s.hmac_secret == "secret-32-bytes-aaaaaaaaaaaaaaaa"
    assert s.approval_base_url == "https://approval.example.workers.dev"
    assert s.post_local_timezone == "America/New_York"
    assert s.post_local_time == "11:00"


def test_post_local_fields_default(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _full_env()
    env.update(
        {
            "BUFFER_ACCESS_TOKEN": "b",
            "BUFFER_LINKEDIN_PROFILE_ID": "p",
            "HMAC_SECRET": "s",
            "APPROVAL_BASE_URL": "u",
        }
    )
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for k in ("POST_LOCAL_TIMEZONE", "POST_LOCAL_TIME"):
        monkeypatch.delenv(k, raising=False)
    s = load_settings()
    assert s.post_local_timezone == "America/New_York"
    assert s.post_local_time == "11:00"
```

Also update the existing `test_load_settings_from_env` and `test_missing_required_var_raises` tests' `_full_env()` should still pass without Phase 2 vars — but `load_settings()` will now raise unless they're present. Update `_full_env()` to include the new required vars (`BUFFER_ACCESS_TOKEN`, `BUFFER_LINKEDIN_PROFILE_ID`, `HMAC_SECRET`, `APPROVAL_BASE_URL`) with dummy strings. Leave `POST_LOCAL_TIMEZONE` and `POST_LOCAL_TIME` out so the default test still works.

Updated `_full_env()`:

```python
def _full_env() -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": "sk-test",
        "UNSPLASH_ACCESS_KEY": "u-test",
        "GMAIL_USERNAME": "a@b.com",
        "GMAIL_APP_PASSWORD": "app-pwd",
        "GMAIL_RECIPIENT": "a@b.com",
        "PROFILE_PATH": "./master_profile.json",
        "DB_PATH": "./db/state.sqlite",
        "LOG_LEVEL": "INFO",
        "BUFFER_ACCESS_TOKEN": "btkn",
        "BUFFER_LINKEDIN_PROFILE_ID": "p1",
        "HMAC_SECRET": "secret-32-bytes-aaaaaaaaaaaaaaaa",
        "APPROVAL_BASE_URL": "https://approval.example.workers.dev",
    }
```

- [ ] **Step 3.2: Update `src/agent/config.py`**

Replace the existing `Settings` and `_REQUIRED` and `load_settings`:

```python
"""Environment-based configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Immutable application settings loaded from environment."""

    model_config = {"frozen": True}

    anthropic_api_key: str = Field(min_length=1)
    unsplash_access_key: str = Field(min_length=1)
    gmail_username: str = Field(min_length=1)
    gmail_app_password: str = Field(min_length=1)
    gmail_recipient: str = Field(min_length=1)
    profile_path: Path
    db_path: Path
    log_level: str = "INFO"

    # Phase 2 — Buffer + approval flow
    buffer_access_token: str = Field(min_length=1)
    buffer_linkedin_profile_id: str = Field(min_length=1)
    hmac_secret: str = Field(min_length=1)
    approval_base_url: str = Field(min_length=1)
    post_local_timezone: str = "America/New_York"
    post_local_time: str = "11:00"  # HH:MM 24h


_REQUIRED = (
    "ANTHROPIC_API_KEY",
    "UNSPLASH_ACCESS_KEY",
    "GMAIL_USERNAME",
    "GMAIL_APP_PASSWORD",
    "GMAIL_RECIPIENT",
    "PROFILE_PATH",
    "DB_PATH",
    "BUFFER_ACCESS_TOKEN",
    "BUFFER_LINKEDIN_PROFILE_ID",
    "HMAC_SECRET",
    "APPROVAL_BASE_URL",
)


def load_settings() -> Settings:
    load_dotenv(override=False)
    missing = [v for v in _REQUIRED if not os.environ.get(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    return Settings(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        unsplash_access_key=os.environ["UNSPLASH_ACCESS_KEY"],
        gmail_username=os.environ["GMAIL_USERNAME"],
        gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
        gmail_recipient=os.environ["GMAIL_RECIPIENT"],
        profile_path=Path(os.environ["PROFILE_PATH"]),
        db_path=Path(os.environ["DB_PATH"]),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        buffer_access_token=os.environ["BUFFER_ACCESS_TOKEN"],
        buffer_linkedin_profile_id=os.environ["BUFFER_LINKEDIN_PROFILE_ID"],
        hmac_secret=os.environ["HMAC_SECRET"],
        approval_base_url=os.environ["APPROVAL_BASE_URL"],
        post_local_timezone=os.environ.get("POST_LOCAL_TIMEZONE", "America/New_York"),
        post_local_time=os.environ.get("POST_LOCAL_TIME", "11:00"),
    )
```

- [ ] **Step 3.3: Update `.env.example`**

Replace existing `.env.example` with:

```
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Unsplash (https://unsplash.com/developers)
UNSPLASH_ACCESS_KEY=

# Gmail SMTP (use a Gmail app password, NOT your main password)
GMAIL_USERNAME=99anujbansal@gmail.com
GMAIL_APP_PASSWORD=
GMAIL_RECIPIENT=99anujbansal@gmail.com

# Profile file path (local dev). In GH Actions, profile is decoded from secret.
PROFILE_PATH=./master_profile.json

# DB
DB_PATH=./db/state.sqlite

# Logging
LOG_LEVEL=INFO

# Buffer (https://publish.buffer.com/developers/apps)
BUFFER_ACCESS_TOKEN=
BUFFER_LINKEDIN_PROFILE_ID=

# Approval flow
HMAC_SECRET=
APPROVAL_BASE_URL=https://approval.<your-name>.workers.dev

# Post scheduling
POST_LOCAL_TIMEZONE=America/New_York
POST_LOCAL_TIME=11:00
```

- [ ] **Step 3.4: Update fixture in tests if any other test relies on `_full_env()` shape**

Verify `pytest -q` still green.

```bash
pytest -q
```

Expected: previous 40 tests still pass + 2 new = 42 passed (after Task 3 alone).

- [ ] **Step 3.5: Commit**

```bash
git add src/agent/config.py .env.example tests/unit/test_config.py
git commit -m "feat(config): add Phase 2 Buffer + approval fields"
```

---

## Task 4: Email template — APPROVE / REJECT buttons

**Files:**
- Modify: `src/agent/delivery/email.py`
- Modify: `tests/unit/test_delivery_email.py`

- [ ] **Step 4.1: Update tests**

Replace the body of `tests/unit/test_delivery_email.py` with:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from agent.delivery.email import build_draft_email, send_email
from agent.db.store import Draft


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
    # Plain
    assert "Hook line." in body_text
    assert "#DataScience" in body_text
    assert "APPROVE: https://approval.example.workers.dev/a?t=APPTOKEN" in body_text
    assert "REJECT: https://approval.example.workers.dev/r?t=REJTOKEN" in body_text
    # HTML
    assert "Hook line." in body_html
    assert 'href="https://approval.example.workers.dev/a?t=APPTOKEN"' in body_html
    assert 'href="https://approval.example.workers.dev/r?t=REJTOKEN"' in body_html
    assert ">APPROVE<" in body_html or "APPROVE" in body_html
    assert ">REJECT<" in body_html or "REJECT" in body_html


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
```

- [ ] **Step 4.2: Update `src/agent/delivery/email.py`**

Change `build_draft_email` signature and bodies:

```python
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
        f'background:{color};color:#fff;font-weight:600;text-decoration:none;'
        f'border-radius:6px;font-family:-apple-system,Segoe UI,Roboto,sans-serif">'
        f'{label}</a>'
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
  <h2 style="margin:0 0 4px 0">LinkedIn Draft — {draft.post_type}</h2>
  <p style="color:#888;margin:0 0 16px 0;font-size:13px">
    Source: {draft.source_ref or '—'} · Draft ID: {draft.id} · Expires: {draft.expires_at}
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
```

- [ ] **Step 4.3: Run tests**

```bash
pytest tests/unit/test_delivery_email.py -v
```

Expected: 2 passed.

- [ ] **Step 4.4: Commit**

```bash
git add src/agent/delivery/email.py tests/unit/test_delivery_email.py
git commit -m "feat(email): APPROVE/REJECT buttons in draft email"
```

---

## Task 5: Wire tokens into the draft pipeline

**Files:**
- Modify: `src/agent/draft.py`
- Modify: `tests/unit/test_draft_pipeline.py`

- [ ] **Step 5.1: Update tests**

Open `tests/unit/test_draft_pipeline.py`. In the `settings` fixture, add the new Phase 2 fields:

```python
@pytest.fixture
def settings(tmp_path: Path, sample_profile_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="x",
        unsplash_access_key="x",
        gmail_username="a@b.com",
        gmail_app_password="x",
        gmail_recipient="a@b.com",
        profile_path=sample_profile_path,
        db_path=tmp_path / "state.sqlite",
        log_level="INFO",
        buffer_access_token="btkn",
        buffer_linkedin_profile_id="p1",
        hmac_secret="secret-32-bytes-aaaaaaaaaaaaaaaa",
        approval_base_url="https://approval.example.workers.dev",
    )
```

Then update the happy-path assertion to verify the email-send-fn was called with an `EmailMessage` whose HTML body contains the approval base URL:

Append a new assertion in `test_run_draft_happy_path`:

```python
    sent_args = send_fn.call_args
    sent_msg = sent_args.args[0] if sent_args.args else sent_args.kwargs.get("msg")
    assert sent_msg is not None
    html = sent_msg.get_body(preferencelist=("html",)).get_content()
    assert "approval.example.workers.dev/a?t=" in html
    assert "approval.example.workers.dev/r?t=" in html
```

- [ ] **Step 5.2: Update `src/agent/draft.py`**

Add imports near the top:

```python
from agent.auth.tokens import sign_token
```

Replace the email-build block in `run_draft` (the section that builds and sends the email) with:

```python
        approve_tok = sign_token(
            draft.id, "approve", ttl_seconds=24 * 3600, secret=settings.hmac_secret
        )
        reject_tok = sign_token(
            draft.id, "reject", ttl_seconds=24 * 3600, secret=settings.hmac_secret
        )
        approve_url = f"{settings.approval_base_url.rstrip('/')}/a?t={approve_tok}"
        reject_url = f"{settings.approval_base_url.rstrip('/')}/r?t={reject_tok}"

        msg = build_draft_email(
            draft=draft,
            sender=settings.gmail_username,
            recipient=settings.gmail_recipient,
            approve_url=approve_url,
            reject_url=reject_url,
        )
        email_send_fn(msg)
```

- [ ] **Step 5.3: Run tests**

```bash
pytest tests/unit/test_draft_pipeline.py -v
```

Expected: 3 passed (existing) — possibly some updates needed if other tests broke.

- [ ] **Step 5.4: Commit**

```bash
git add src/agent/draft.py tests/unit/test_draft_pipeline.py
git commit -m "feat(draft): generate signed approval/reject tokens and embed in email"
```

---

## Task 6: Post pipeline (approve / reject)

**Files:**
- Create: `src/agent/post.py`
- Test: `tests/unit/test_post_pipeline.py`

- [ ] **Step 6.1: Write the failing tests**

`tests/unit/test_post_pipeline.py`:

```python
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from agent.config import Settings
from agent.db.store import Draft, get_draft, init_db, insert_draft
from agent.post import PostResult, next_scheduled_at_utc, run_post


@pytest.fixture
def settings(tmp_path: Path, sample_profile_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="x",
        unsplash_access_key="x",
        gmail_username="a@b.com",
        gmail_app_password="x",
        gmail_recipient="a@b.com",
        profile_path=sample_profile_path,
        db_path=tmp_path / "state.sqlite",
        log_level="INFO",
        buffer_access_token="btkn",
        buffer_linkedin_profile_id="p1",
        hmac_secret="s",
        approval_base_url="https://x",
        post_local_timezone="America/New_York",
        post_local_time="11:00",
    )


def _seed_draft(db_path: Path, status: str = "pending") -> str:
    conn = init_db(db_path)
    insert_draft(
        conn,
        Draft(
            id="d-1",
            post_type="project",
            source_ref="project:p1",
            caption="hi",
            hashtags="#A",
            image_url="http://img",
            image_credit="cred",
            status=status,
        ),
    )
    conn.close()
    return "d-1"


def test_next_scheduled_at_utc_picks_next_11am_et() -> None:
    # Friday 2026-05-15 09:00 ET. Next 11:00 ET = same day 11:00 ET = 15:00 UTC (EDT).
    nyc = ZoneInfo("America/New_York")
    now_local = datetime(2026, 5, 15, 9, 0, tzinfo=nyc)
    when = next_scheduled_at_utc(now_local, "America/New_York", time(11, 0))
    assert when.tzinfo is not None
    assert when.utcoffset().total_seconds() == 0  # UTC
    # 11:00 EDT = 15:00 UTC
    assert when.hour == 15
    assert when.minute == 0


def test_next_scheduled_at_utc_rolls_over_after_11am() -> None:
    nyc = ZoneInfo("America/New_York")
    now_local = datetime(2026, 5, 15, 12, 0, tzinfo=nyc)
    when = next_scheduled_at_utc(now_local, "America/New_York", time(11, 0))
    # Rolls to next day
    assert when.day == 16


@freeze_time("2026-05-15T13:00:00Z")
def test_run_post_approve_schedules_buffer(settings: Settings) -> None:
    _seed_draft(settings.db_path)

    buffer_fn = MagicMock(return_value="upd123")
    email_fn = MagicMock()
    result = run_post(
        settings,
        draft_id="d-1",
        action="approve",
        buffer_schedule_fn=buffer_fn,
        email_send_fn=email_fn,
    )
    assert isinstance(result, PostResult)
    assert result.status == "posted"
    buffer_fn.assert_called_once()
    # Email confirmation sent
    email_fn.assert_called_once()

    conn = init_db(settings.db_path)
    d = get_draft(conn, "d-1")
    conn.close()
    assert d is not None
    assert d.status == "posted"
    assert d.buffer_post_id == "upd123"


@freeze_time("2026-05-15T13:00:00Z")
def test_run_post_reject_marks_rejected(settings: Settings) -> None:
    _seed_draft(settings.db_path)

    buffer_fn = MagicMock()
    email_fn = MagicMock()
    result = run_post(
        settings,
        draft_id="d-1",
        action="reject",
        buffer_schedule_fn=buffer_fn,
        email_send_fn=email_fn,
    )
    assert result.status == "rejected"
    buffer_fn.assert_not_called()
    email_fn.assert_called_once()

    conn = init_db(settings.db_path)
    d = get_draft(conn, "d-1")
    conn.close()
    assert d is not None
    assert d.status == "rejected"


def test_run_post_idempotent_when_already_posted(settings: Settings) -> None:
    _seed_draft(settings.db_path, status="posted")
    buffer_fn = MagicMock()
    email_fn = MagicMock()
    result = run_post(
        settings,
        draft_id="d-1",
        action="approve",
        buffer_schedule_fn=buffer_fn,
        email_send_fn=email_fn,
    )
    assert result.status == "noop"
    buffer_fn.assert_not_called()


def test_run_post_unknown_draft_errors(settings: Settings) -> None:
    init_db(settings.db_path).close()
    buffer_fn = MagicMock()
    email_fn = MagicMock()
    result = run_post(
        settings,
        draft_id="missing",
        action="approve",
        buffer_schedule_fn=buffer_fn,
        email_send_fn=email_fn,
    )
    assert result.status == "error"
    buffer_fn.assert_not_called()
```

- [ ] **Step 6.2: Verify failure**

```bash
pytest tests/unit/test_post_pipeline.py -v
```

Expected: ImportError on `agent.post`.

- [ ] **Step 6.3: Implement `src/agent/post.py`**

```python
"""Post pipeline entrypoint: approve schedules on Buffer; reject marks draft."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from email.message import EmailMessage
from typing import Any
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
    m["Subject"] = f"[LinkedIn] {action} — {draft_id}"
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

    buffer_schedule_fn = buffer_schedule_fn or (
        lambda **kwargs: schedule_update(**kwargs)
    )
    email_send_fn = email_send_fn or (
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
            log.info("Draft %s already in status %s — no-op", draft_id, draft.status)
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
            email_send_fn(msg)
            return PostResult(status="rejected", draft_id=draft_id)

        # action == "approve"
        hour, minute = (int(part) for part in settings.post_local_time.split(":", 1))
        target = time(hour=hour, minute=minute)
        now_local = datetime.now(ZoneInfo(settings.post_local_timezone))
        when = next_scheduled_at_utc(now_local, settings.post_local_timezone, target)

        post_text = f"{draft.caption}\n\n{draft.hashtags}"
        buffer_post_id = buffer_schedule_fn(
            access_token=settings.buffer_access_token,
            profile_id=settings.buffer_linkedin_profile_id,
            text=post_text,
            media_link=draft.image_url,
            scheduled_at=when,
        )

        conn.execute(
            "UPDATE drafts SET status = 'posted', buffer_post_id = ?, posted_at = ? WHERE id = ?",
            (buffer_post_id, datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"), draft_id),
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
        email_send_fn(msg)
        return PostResult(status="posted", draft_id=draft_id, buffer_post_id=buffer_post_id)
    finally:
        conn.close()
```

- [ ] **Step 6.4: Run tests**

```bash
pytest tests/unit/test_post_pipeline.py -v
```

Expected: 6 passed.

- [ ] **Step 6.5: Commit**

```bash
git add src/agent/post.py tests/unit/test_post_pipeline.py
git commit -m "feat(post): approve/reject pipeline with Buffer scheduling"
```

---

## Task 7: CLI — `post` subcommand

**Files:**
- Modify: `src/agent/__main__.py`

- [ ] **Step 7.1: Update CLI**

Replace `src/agent/__main__.py`:

```python
"""`python -m agent` dispatcher."""

from __future__ import annotations

import argparse
import sys

from anthropic import Anthropic

from agent.config import load_settings
from agent.db.store import init_db, list_pending, update_draft_status
from agent.draft import run_draft
from agent.logging_setup import setup_logging
from agent.post import run_post


def _cmd_draft(args: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    client = Anthropic(api_key=settings.anthropic_api_key)
    result = run_draft(
        settings,
        anthropic_client=client,
        force=args.force,
        override_post_type=args.post_type,
        dry_run=args.dry_run,
    )
    print(f"status={result.status} post_type={result.post_type} draft_id={result.draft_id}")
    return 0 if result.status in ("drafted", "skipped", "dry_run") else 1


def _cmd_post(args: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    result = run_post(settings, draft_id=args.draft_id, action=args.action)
    print(
        f"status={result.status} draft_id={result.draft_id} "
        f"buffer_post_id={result.buffer_post_id} message={result.message}"
    )
    return 0 if result.status in ("posted", "rejected", "noop") else 1


def _cmd_db_list_pending(_: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    conn = init_db(settings.db_path)
    try:
        for d in list_pending(conn):
            print(f"{d.id}\t{d.post_type}\t{d.source_ref}\t{d.expires_at}")
    finally:
        conn.close()
    return 0


def _cmd_db_expire(args: argparse.Namespace) -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    conn = init_db(settings.db_path)
    try:
        update_draft_status(conn, args.draft_id, "expired")
        print(f"marked {args.draft_id} expired")
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    draft = sub.add_parser("draft", help="Generate today's draft.")
    draft.add_argument("--dry-run", action="store_true")
    draft.add_argument("--force", action="store_true")
    draft.add_argument("--post-type", choices=["project", "concept", "career"])
    draft.set_defaults(func=_cmd_draft)

    post = sub.add_parser("post", help="Approve or reject a draft.")
    post.add_argument("--draft-id", required=True)
    post.add_argument("--action", required=True, choices=["approve", "reject"])
    post.set_defaults(func=_cmd_post)

    db = sub.add_parser("db", help="Inspect the SQLite state.")
    db_sub = db.add_subparsers(dest="db_cmd", required=True)

    list_p = db_sub.add_parser("list-pending")
    list_p.set_defaults(func=_cmd_db_list_pending)

    expire_p = db_sub.add_parser("expire")
    expire_p.add_argument("draft_id")
    expire_p.set_defaults(func=_cmd_db_expire)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7.2: Sanity check**

```bash
python -m agent post --help
python -m agent --help
```

Expected: clean usage output.

- [ ] **Step 7.3: Commit**

```bash
git add src/agent/__main__.py
git commit -m "feat(cli): add `post` subcommand for approve/reject"
```

---

## Task 8: Cloudflare Worker source

**Files:**
- Create: `worker/approval.js`
- Create: `worker/wrangler.toml`
- Create: `worker/package.json`
- Create: `worker/README.md`

- [ ] **Step 8.1: Create `worker/approval.js`**

```javascript
// Cloudflare Worker: receives APPROVE/REJECT clicks from draft email,
// verifies HMAC token, dispatches the GitHub Actions `post.yml` workflow.
//
// Required environment (set via `wrangler secret put`):
//   - HMAC_SECRET            (same value as the Python agent's HMAC_SECRET)
//   - GH_PAT                 (fine-grained PAT with `actions:write` on the repo)
//   - GH_REPO                ("owner/name", e.g. "99anujb/linkedin-agent")
//   - GH_WORKFLOW_FILE       ("post.yml")
//   - GH_REF                 (branch to dispatch on, e.g. "main")

const VALID_ACTIONS = new Set(["approve", "reject"]);

function b64urlDecodeToBytes(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4;
  if (pad) s += "=".repeat(4 - pad);
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function verifyToken(token, secret) {
  const dot = token.indexOf(".");
  if (dot < 1) throw new Error("malformed token");
  const payloadB64 = token.slice(0, dot);
  const sigB64 = token.slice(dot + 1);

  const payloadBytes = b64urlDecodeToBytes(payloadB64);
  const sigBytes = b64urlDecodeToBytes(sigB64);

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
  const ok = await crypto.subtle.verify("HMAC", key, sigBytes, payloadBytes);
  if (!ok) throw new Error("bad signature");

  const text = new TextDecoder().decode(payloadBytes);
  const parts = text.split("|");
  if (parts.length !== 3) throw new Error("malformed payload");
  const [draftId, action, expiresStr] = parts;
  if (!VALID_ACTIONS.has(action)) throw new Error("bad action");
  const expires = parseInt(expiresStr, 10);
  if (!Number.isFinite(expires)) throw new Error("bad expiry");
  if (Math.floor(Date.now() / 1000) > expires) throw new Error("token expired");
  return { draftId, action };
}

async function dispatchWorkflow(env, draftId, action) {
  const url = `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${env.GH_WORKFLOW_FILE}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_PAT}`,
      "User-Agent": "linkedin-agent-approval-worker",
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ref: env.GH_REF,
      inputs: { draft_id: draftId, action },
    }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`github dispatch failed: ${resp.status} ${body}`);
  }
}

function htmlPage(title, body, color = "#0a66c2") {
  return new Response(
    `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title></head>
     <body style="font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f7f7f9">
       <div style="max-width:480px;padding:32px;background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.06)">
         <h2 style="color:${color};margin-top:0">${title}</h2>
         <p style="color:#444">${body}</p>
       </div>
     </body></html>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response("OK", { status: 200 });
    }
    const expectedAction =
      url.pathname === "/a" ? "approve"
      : url.pathname === "/r" ? "reject"
      : null;
    if (expectedAction === null) return new Response("not found", { status: 404 });

    const token = url.searchParams.get("t");
    if (!token) return htmlPage("Missing token", "No token provided.", "#b91c1c");

    let payload;
    try {
      payload = await verifyToken(token, env.HMAC_SECRET);
    } catch (e) {
      const msg = String(e.message || e);
      const status = msg.includes("expired") ? "Token expired" : "Invalid token";
      return htmlPage(status, "This approval link is no longer valid.", "#b91c1c");
    }

    if (payload.action !== expectedAction) {
      return htmlPage("Action mismatch", "The token does not match this URL.", "#b91c1c");
    }

    try {
      await dispatchWorkflow(env, payload.draftId, payload.action);
    } catch (e) {
      return htmlPage("Dispatch failed", String(e.message || e), "#b91c1c");
    }

    const verb = payload.action === "approve" ? "approved" : "rejected";
    return htmlPage(
      `Draft ${verb}`,
      payload.action === "approve"
        ? "Buffer will publish at the configured local time."
        : "Draft skipped. The cron will draft a new one tomorrow.",
      payload.action === "approve" ? "#0a66c2" : "#6b7280",
    );
  },
};
```

- [ ] **Step 8.2: Create `worker/wrangler.toml`**

```toml
name = "linkedin-agent-approval"
main = "approval.js"
compatibility_date = "2026-04-01"

# Secrets are set via `wrangler secret put` rather than declared here:
#   wrangler secret put HMAC_SECRET
#   wrangler secret put GH_PAT
#   wrangler secret put GH_REPO          # e.g. 99anujb/linkedin-agent
#   wrangler secret put GH_WORKFLOW_FILE # post.yml
#   wrangler secret put GH_REF           # main
```

- [ ] **Step 8.3: Create `worker/package.json`**

```json
{
  "name": "linkedin-agent-approval-worker",
  "version": "0.1.0",
  "private": true,
  "devDependencies": {
    "wrangler": "^3.78.0"
  },
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy"
  }
}
```

- [ ] **Step 8.4: Create `worker/README.md`**

````markdown
# Approval Worker

Cloudflare Worker that receives approve/reject clicks from the draft email
and dispatches the `post.yml` GitHub Actions workflow.

## One-time setup

1. Install Node 20+ if you don't have it.
2. Install wrangler:

   ```
   cd worker
   npm install
   ```

3. Log in to Cloudflare:

   ```
   npx wrangler login
   ```

4. Set secrets (you'll be prompted for each value):

   ```
   npx wrangler secret put HMAC_SECRET        # same value as the agent's HMAC_SECRET
   npx wrangler secret put GH_PAT             # fine-grained PAT, actions:write
   npx wrangler secret put GH_REPO            # 99anujb/linkedin-agent
   npx wrangler secret put GH_WORKFLOW_FILE   # post.yml
   npx wrangler secret put GH_REF             # main
   ```

5. Deploy:

   ```
   npx wrangler deploy
   ```

   wrangler prints the deployed URL, e.g.
   `https://linkedin-agent-approval.<your-name>.workers.dev`.
   Set that as `APPROVAL_BASE_URL` in `.env` and as a repo secret.

## Smoke test

```
curl https://linkedin-agent-approval.<your-name>.workers.dev/health
# → OK
```

A valid approve URL has the shape:

```
https://linkedin-agent-approval.<your-name>.workers.dev/a?t=<token>
```

Without `t`, the worker returns "Missing token" (HTTP 200, HTML body).
````

- [ ] **Step 8.5: Update repo `.gitignore`**

Append to `.gitignore`:

```
# Cloudflare Worker
worker/node_modules/
worker/.wrangler/
```

- [ ] **Step 8.6: Commit**

```bash
git add worker/ .gitignore
git commit -m "feat(worker): Cloudflare Worker for approve/reject clicks"
```

---

## Task 9: `post.yml` GitHub Actions workflow

**Files:**
- Create: `.github/workflows/post.yml`

- [ ] **Step 9.1: Implement**

```yaml
name: post
on:
  workflow_dispatch:
    inputs:
      draft_id:
        description: "Draft UUID from SQLite"
        required: true
      action:
        description: "approve | reject"
        required: true
        type: choice
        options:
          - approve
          - reject

jobs:
  post:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - run: pip install -e .

      - name: Decode profile from secret
        env:
          PROFILE_B64: ${{ secrets.PROFILE_B64 }}
        run: |
          if [ -z "$PROFILE_B64" ]; then echo "PROFILE_B64 missing"; exit 1; fi
          echo "$PROFILE_B64" | base64 -d > master_profile.json

      - name: Run post
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          UNSPLASH_ACCESS_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}
          GMAIL_USERNAME: ${{ secrets.GMAIL_USERNAME }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          GMAIL_RECIPIENT: ${{ secrets.GMAIL_RECIPIENT }}
          PROFILE_PATH: ./master_profile.json
          DB_PATH: ./db/state.sqlite
          LOG_LEVEL: INFO
          BUFFER_ACCESS_TOKEN: ${{ secrets.BUFFER_ACCESS_TOKEN }}
          BUFFER_LINKEDIN_PROFILE_ID: ${{ secrets.BUFFER_LINKEDIN_PROFILE_ID }}
          HMAC_SECRET: ${{ secrets.HMAC_SECRET }}
          APPROVAL_BASE_URL: ${{ secrets.APPROVAL_BASE_URL }}
        run: |
          python -m agent post \
            --draft-id "${{ inputs.draft_id }}" \
            --action "${{ inputs.action }}"

      - name: Wipe decoded profile
        if: always()
        run: rm -f master_profile.json

      - name: Commit updated state DB
        run: |
          git config user.name "linkedin-agent"
          git config user.email "noreply@anthropic.com"
          if git diff --quiet db/state.sqlite; then
            echo "no DB changes to commit"
          else
            git add db/state.sqlite
            git commit -m "chore(db): state after post ${{ inputs.action }} of ${{ inputs.draft_id }}"
            git push
          fi
```

- [ ] **Step 9.2: Verify YAML**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/post.yml'))"
```

Expected: no exception.

- [ ] **Step 9.3: Commit**

```bash
git add .github/workflows/post.yml
git commit -m "ci(post): workflow_dispatch for approve/reject"
```

---

## Task 10: Buffer profile-discovery helper

**Files:**
- Create: `scripts/discover_buffer_profile.py`

- [ ] **Step 10.1: Implement**

```python
"""One-time helper: print Buffer profile IDs for each connected channel.

Usage:
    python -m scripts.discover_buffer_profile
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from agent.delivery.buffer import list_profiles


def main() -> int:
    load_dotenv()
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        print("BUFFER_ACCESS_TOKEN missing in environment / .env", file=sys.stderr)
        return 1
    profiles = list_profiles(access_token=token)
    if not profiles:
        print("No connected channels found.", file=sys.stderr)
        return 1
    print("service\tid\tusername")
    for p in profiles:
        print(f"{p.service}\t{p.id}\t{p.username}")
    print(
        "\nCopy the `id` for service=linkedin into .env as "
        "BUFFER_LINKEDIN_PROFILE_ID.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 10.2: Make `scripts/` a package**

`scripts/__init__.py`: empty.

- [ ] **Step 10.3: Commit**

```bash
git add scripts/
git commit -m "feat(scripts): Buffer profile-id discovery helper"
```

---

## Task 11: Full-suite green + lint/type clean

- [ ] **Step 11.1: Run all checks**

```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest -q
```

If `ruff format --check` fails, run `ruff format src tests`. Re-run all four. Commit any formatting fixes in a single chore commit:

```bash
git add -A
git commit -m "chore: ruff format after Phase 2 implementation"
```

Expected end-state: all four commands clean, pytest ≥ 50 passed.

---

## Task 12: README — Phase 2 deploy walkthrough

**Files:**
- Modify: `README.md`

- [ ] **Step 12.1: Append a Phase 2 section**

Read `README.md`, then append (after the Phase 1 deploy section):

````markdown
## Phase 2: Buffer + Cloudflare Worker

Phase 2 adds APPROVE / REJECT buttons in the draft email. Clicking a button
hits a Cloudflare Worker that triggers a `post.yml` GitHub Actions workflow,
which schedules the post on Buffer for 11:00 ET.

### One-time setup

1. **Buffer.** Create a free Buffer account, connect your LinkedIn profile,
   then create an API access token at
   `https://publish.buffer.com/developers/apps`.

2. **Discover your Buffer LinkedIn profile id.** Locally:

   ```
   python -m scripts.discover_buffer_profile
   ```

   Copy the `id` for the `linkedin` row into `.env` as
   `BUFFER_LINKEDIN_PROFILE_ID`.

3. **HMAC secret.** Generate a 32-byte secret:

   ```
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Put it in `.env` as `HMAC_SECRET`. (We'll mirror it to GitHub and Cloudflare.)

4. **Fine-grained GitHub PAT.** Create at
   `https://github.com/settings/personal-access-tokens/new`:
   - Resource owner: your account
   - Repository access: only `linkedin-agent`
   - Permissions → Actions: **Read and write**
   Copy the token; you'll need it for Cloudflare.

5. **Deploy the Worker.** See `worker/README.md`.

   After deploy, copy the printed URL (e.g.
   `https://linkedin-agent-approval.<your-name>.workers.dev`) into `.env` as
   `APPROVAL_BASE_URL`.

6. **Mirror Phase 2 secrets to GitHub** (so `post.yml` can read them):

   - `BUFFER_ACCESS_TOKEN`
   - `BUFFER_LINKEDIN_PROFILE_ID`
   - `HMAC_SECRET`
   - `APPROVAL_BASE_URL`

   Update each via the GitHub UI or via `gh secret set`:

   ```
   gh secret set BUFFER_ACCESS_TOKEN --repo 99anujb/linkedin-agent
   gh secret set BUFFER_LINKEDIN_PROFILE_ID --repo 99anujb/linkedin-agent
   gh secret set HMAC_SECRET --repo 99anujb/linkedin-agent
   gh secret set APPROVAL_BASE_URL --repo 99anujb/linkedin-agent
   ```

### End-to-end test

1. Trigger a fresh draft from Actions (or wait for the cron).
2. Open the draft email; verify it now shows APPROVE and REJECT buttons.
3. Click APPROVE; the Worker should redirect to a success page.
4. Check `https://github.com/99anujb/linkedin-agent/actions` — `post.yml` is
   running.
5. After the workflow succeeds, log in to Buffer; the post should appear in
   the Queue scheduled for the next 11:00 ET slot.
6. Wait until the scheduled time and verify the post lands on LinkedIn.
````

- [ ] **Step 12.2: Commit**

```bash
git add README.md
git commit -m "docs(readme): Phase 2 Buffer + Worker deploy walkthrough"
```

---

## Task 13: User-facing setup checklist (no code)

This task is a **manual** checklist for the human, not for the implementer. After all code tasks are done, the user does:

- [ ] Phase 1 still healthy (`gh run list --workflow=draft.yml`).
- [ ] Generate `HMAC_SECRET` and add to `.env`.
- [ ] Sign up Cloudflare account; install wrangler (`cd worker && npm install`).
- [ ] Create fine-grained GitHub PAT scoped `actions:write` on `linkedin-agent`.
- [ ] `cd worker && npx wrangler login && npx wrangler secret put …` (5 secrets).
- [ ] `npx wrangler deploy` and copy the URL.
- [ ] Run `python -m scripts.discover_buffer_profile`; paste the LinkedIn id into `.env`.
- [ ] Add all Phase 2 secrets (Buffer token, LinkedIn profile id, HMAC, APPROVAL_BASE_URL) to GitHub via `gh secret set`.
- [ ] Trigger `draft.yml` manually; check the email has working APPROVE/REJECT buttons.
- [ ] Click APPROVE in the email; verify Buffer queue receives a scheduled post.
- [ ] Wait for the scheduled time; verify it published on LinkedIn.

---

## Final verification

- [ ] `pytest` ≥ 50 passed, all green.
- [ ] `ruff check`, `ruff format --check`, `mypy` all clean.
- [ ] Manual cloud test of `draft.yml` → email has buttons.
- [ ] Manual APPROVE click → Worker page renders → `post.yml` runs successfully.
- [ ] Buffer queue shows the scheduled post.
- [ ] Real LinkedIn post lands at the scheduled time.

When all boxes are checked, Phase 2 is shipped.
