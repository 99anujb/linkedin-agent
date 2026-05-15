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
