from __future__ import annotations

from datetime import UTC, datetime

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
    when = datetime(2026, 5, 16, 15, 0, tzinfo=UTC)
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
    assert b"scheduled_at=1778943600" in sent.content
    assert b"hello" in sent.content
    assert b"media%5Blink%5D=https%3A%2F%2Fimages.example%2Fx.jpg" in sent.content


@respx.mock
def test_schedule_update_buffer_error_raises() -> None:
    respx.post("https://api.bufferapp.com/1/updates/create.json").mock(
        return_value=httpx.Response(403, json={"error": "rate limited"})
    )
    when = datetime(2026, 5, 16, 15, 0, tzinfo=UTC)
    with pytest.raises(BufferError, match="403"):
        schedule_update(
            access_token="tkn",
            profile_id="p1",
            text="x",
            media_link=None,
            scheduled_at=when,
        )
