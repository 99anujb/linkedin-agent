from __future__ import annotations

import json
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

GRAPHQL_URL = "https://api.buffer.com"


def _graphql_router(responses: list[dict]) -> respx.MockRouter:
    """Mock the single GraphQL endpoint to return responses in order per call."""
    route = respx.post(GRAPHQL_URL).mock(
        side_effect=[httpx.Response(200, json=r) for r in responses]
    )
    return route


@respx.mock
def test_list_profiles_returns_channels_mapped_to_buffer_profiles() -> None:
    route = _graphql_router(
        [
            {"data": {"account": {"organizations": [{"id": "org_abc"}]}}},
            {
                "data": {
                    "channels": [
                        {"id": "ch1", "name": "anuj", "service": "linkedin"},
                        {"id": "ch2", "name": "anuj-tw", "service": "twitter"},
                    ]
                }
            },
        ]
    )

    profiles = list_profiles(access_token="tkn")

    assert profiles == [
        BufferProfile(id="ch1", service="linkedin", username="anuj"),
        BufferProfile(id="ch2", service="twitter", username="anuj-tw"),
    ]
    assert route.call_count == 2
    first_body = json.loads(route.calls[0].request.content)
    assert "account" in first_body["query"]
    second_body = json.loads(route.calls[1].request.content)
    assert "channels" in second_body["query"]
    assert "OrganizationId!" in second_body["query"]
    assert second_body["variables"]["organizationId"] == "org_abc"
    auth = route.calls[0].request.headers["authorization"]
    assert auth == "Bearer tkn"


@respx.mock
def test_list_profiles_http_error_raises() -> None:
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(401, json={"error": "bad token"}))
    with pytest.raises(BufferError, match="401"):
        list_profiles(access_token="tkn")


@respx.mock
def test_list_profiles_graphql_error_raises() -> None:
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "Unauthorized"}]},
        )
    )
    with pytest.raises(BufferError, match="Unauthorized"):
        list_profiles(access_token="tkn")


@respx.mock
def test_list_profiles_no_organizations_raises() -> None:
    _graphql_router([{"data": {"account": {"organizations": []}}}])
    with pytest.raises(BufferError, match="no organizations"):
        list_profiles(access_token="tkn")


@respx.mock
def test_schedule_update_sends_createpost_mutation() -> None:
    route = respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "createPost": {
                        "__typename": "PostActionSuccess",
                        "post": {"id": "post_123"},
                    }
                }
            },
        )
    )
    when = datetime(2026, 5, 16, 15, 0, tzinfo=UTC)

    update_id = schedule_update(
        access_token="tkn",
        profile_id="ch1",
        text="hello\n\n#A #B",
        media_link="https://images.example/x.jpg",
        scheduled_at=when,
    )

    assert update_id == "post_123"
    sent = json.loads(route.calls.last.request.content)
    assert "createPost" in sent["query"]
    inp = sent["variables"]["input"]
    assert inp["channelId"] == "ch1"
    assert inp["text"] == "hello\n\n#A #B"
    assert inp["dueAt"] == "2026-05-16T15:00:00+00:00"
    assert inp["schedulingType"] == "automatic"
    assert inp["mode"] == "customScheduled"
    assert inp["assets"] == [
        {
            "image": {
                "url": "https://images.example/x.jpg",
                "thumbnailUrl": "https://images.example/x.jpg",
            }
        }
    ]
    assert route.calls.last.request.headers["authorization"] == "Bearer tkn"


@respx.mock
def test_schedule_update_without_media_omits_assets() -> None:
    route = respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "createPost": {
                        "__typename": "PostActionSuccess",
                        "post": {"id": "p"},
                    }
                }
            },
        )
    )
    when = datetime(2026, 5, 16, 15, 0, tzinfo=UTC)

    schedule_update(
        access_token="tkn",
        profile_id="ch1",
        text="x",
        media_link=None,
        scheduled_at=when,
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent["variables"]["input"]["assets"] == []
    assert sent["variables"]["input"]["mode"] == "customScheduled"
    assert sent["variables"]["input"]["schedulingType"] == "automatic"


@respx.mock
def test_schedule_update_http_error_raises() -> None:
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(403, json={"error": "rate limited"}))
    when = datetime(2026, 5, 16, 15, 0, tzinfo=UTC)
    with pytest.raises(BufferError, match="403"):
        schedule_update(
            access_token="tkn",
            profile_id="ch1",
            text="x",
            media_link=None,
            scheduled_at=when,
        )


@respx.mock
def test_schedule_update_mutation_error_raises() -> None:
    respx.post(GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "createPost": {
                        "__typename": "MutationError",
                        "message": "Channel disconnected",
                    }
                }
            },
        )
    )
    when = datetime(2026, 5, 16, 15, 0, tzinfo=UTC)
    with pytest.raises(BufferError, match="Channel disconnected"):
        schedule_update(
            access_token="tkn",
            profile_id="ch1",
            text="x",
            media_link=None,
            scheduled_at=when,
        )
