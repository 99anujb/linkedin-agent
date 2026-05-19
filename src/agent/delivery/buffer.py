"""Buffer GraphQL API client (Personal API Key compatible)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

BUFFER_GRAPHQL_URL = "https://api.buffer.com"
log = logging.getLogger(__name__)


class BufferError(Exception):
    """Buffer API returned a non-2xx status, GraphQL errors, or a mutation failure."""


@dataclass(frozen=True)
class BufferProfile:
    id: str
    service: str
    username: str


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _post_graphql(
    *, access_token: str, query: str, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    resp = httpx.post(
        BUFFER_GRAPHQL_URL,
        headers=_headers(access_token),
        json=payload,
        timeout=15.0,
    )
    if resp.status_code != 200:
        raise BufferError(f"Buffer GraphQL returned {resp.status_code}: {resp.text}")
    body = resp.json()
    if body.get("errors"):
        messages = "; ".join(e.get("message", "?") for e in body["errors"])
        raise BufferError(f"Buffer GraphQL errors: {messages}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise BufferError(f"Buffer GraphQL missing data: {body}")
    return data


_ACCOUNT_ORG_QUERY = """
query {
  account {
    organizations { id }
  }
}
""".strip()


_CHANNELS_QUERY = """
query Channels($organizationId: OrganizationId!) {
  channels(input: {organizationId: $organizationId}) {
    id
    name
    service
  }
}
""".strip()


def list_profiles(*, access_token: str) -> list[BufferProfile]:
    """Return all channels connected to the Buffer account."""
    log.info("Fetching Buffer account organizations")
    account_data = _post_graphql(access_token=access_token, query=_ACCOUNT_ORG_QUERY)
    orgs = (account_data.get("account") or {}).get("organizations") or []
    if not orgs:
        raise BufferError("Buffer account has no organizations")
    organization_id = orgs[0]["id"]

    log.info("Listing Buffer channels for organization %s", organization_id)
    channels_data = _post_graphql(
        access_token=access_token,
        query=_CHANNELS_QUERY,
        variables={"organizationId": organization_id},
    )
    channels = channels_data.get("channels") or []
    return [
        BufferProfile(
            id=ch["id"],
            service=ch.get("service", ""),
            username=ch.get("name", ""),
        )
        for ch in channels
    ]


_CREATE_POST_MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id } }
    ... on MutationError { message }
  }
}
""".strip()


def schedule_update(
    *,
    access_token: str,
    profile_id: str,
    text: str,
    media_link: str | None,
    scheduled_at: datetime,
) -> str:
    """Schedule a single post on Buffer. Returns the post id."""
    assets: list[dict[str, str]] = (
        [
            {
                "type": "image",
                "url": media_link,
                "thumbnailUrl": media_link,
            }
        ]
        if media_link
        else []
    )
    input_payload: dict[str, Any] = {
        "channelId": profile_id,
        "text": text,
        "schedulingType": "automatic",
        "mode": "customScheduled",
        "dueAt": scheduled_at.isoformat(),
        "assets": assets,
    }
    log.info(
        "Scheduling Buffer post on channel=%s dueAt=%s",
        profile_id,
        input_payload["dueAt"],
    )
    data = _post_graphql(
        access_token=access_token,
        query=_CREATE_POST_MUTATION,
        variables={"input": input_payload},
    )
    result = data.get("createPost") or {}
    typename = result.get("__typename")
    if typename == "MutationError":
        raise BufferError(f"createPost failed: {result.get('message', 'unknown')}")
    post = result.get("post") or {}
    post_id = post.get("id")
    if not post_id:
        raise BufferError(f"createPost returned no post id: {data}")
    return str(post_id)
