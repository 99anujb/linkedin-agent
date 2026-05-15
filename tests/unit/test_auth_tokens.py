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
