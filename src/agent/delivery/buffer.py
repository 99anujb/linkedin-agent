"""Minimal Buffer Classic API client (free-plan compatible)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

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
    encoded = urlencode(data).encode()
    headers = {**_auth_headers(access_token), "Content-Type": "application/x-www-form-urlencoded"}
    resp = httpx.post(url, headers=headers, content=encoded, timeout=15.0)
    if resp.status_code != 200:
        raise BufferError(f"updates/create.json returned {resp.status_code}: {resp.text}")
    body = resp.json()
    if not body.get("success"):
        raise BufferError(f"updates/create.json not successful: {body}")
    updates = body.get("updates") or []
    if not updates:
        raise BufferError(f"no updates returned: {body}")
    return str(updates[0]["id"])
