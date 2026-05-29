"""Fetch trending AI / data-science headlines from RSS feeds.

Used by trending + news_take post types. Headlines that have already been
used are persisted in `seen_headlines` so we never re-post the same news.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from agent.db.store import record_seen_headline, seen_headline_hashes

log = logging.getLogger(__name__)

DEFAULT_FEEDS: tuple[tuple[str, str], ...] = (
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
    ("MIT Technology Review AI", "https://www.technologyreview.com/feed/"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("Towards Data Science", "https://towardsdatascience.com/feed"),
    ("KDnuggets", "https://www.kdnuggets.com/feed"),
)

FETCH_TIMEOUT = 12.0


@dataclass(frozen=True)
class Headline:
    title: str
    summary: str
    link: str
    source: str

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.title.strip().lower().encode("utf-8")).hexdigest()[:16]


def _parse_rss(xml_bytes: bytes, source_name: str) -> list[Headline]:
    """Parse an RSS or Atom feed and return up to 20 entries."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log.warning("RSS parse failed for %s: %s", source_name, e)
        return []

    items: list[Headline] = []
    # RSS 2.0: channel/item
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        if title:
            items.append(Headline(title=title, summary=desc, link=link, source=source_name))
        if len(items) >= 20:
            break
    if items:
        return items

    # Atom: entry/title|link|summary
    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.iter(f"{atom_ns}entry"):
        title = (entry.findtext(f"{atom_ns}title") or "").strip()
        link_el = entry.find(f"{atom_ns}link")
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        summary = (entry.findtext(f"{atom_ns}summary") or "").strip()
        if title:
            items.append(Headline(title=title, summary=summary, link=link, source=source_name))
        if len(items) >= 20:
            break
    return items


def _fetch_one(name: str, url: str, *, client: httpx.Client | None = None) -> list[Headline]:
    try:
        if client is None:
            resp = httpx.get(url, timeout=FETCH_TIMEOUT, follow_redirects=True)
        else:
            resp = client.get(url, timeout=FETCH_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("RSS fetch failed for %s (%s): %s", name, url, e)
        return []
    return _parse_rss(resp.content, name)


def parse_feeds_env(raw: str) -> list[tuple[str, str]]:
    """Parse RSS_FEEDS env value: comma-separated 'Name|URL' pairs."""
    out: list[tuple[str, str]] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or "|" not in chunk:
            continue
        name, _, url = chunk.partition("|")
        name, url = name.strip(), url.strip()
        if name and url:
            out.append((name, url))
    return out


def _resolve_feeds(feeds: list[tuple[str, str]] | None) -> list[tuple[str, str]]:
    if feeds:
        return feeds
    env_raw = os.environ.get("RSS_FEEDS", "").strip()
    if env_raw:
        parsed = parse_feeds_env(env_raw)
        if parsed:
            return parsed
    return list(DEFAULT_FEEDS)


def fetch_headlines(
    *,
    feeds: list[tuple[str, str]] | None = None,
    client: httpx.Client | None = None,
) -> list[Headline]:
    """Return headlines from all feeds. Errors per feed are tolerated."""
    resolved = _resolve_feeds(feeds)
    out: list[Headline] = []
    for name, url in resolved:
        out.extend(_fetch_one(name, url, client=client))
    log.info("Fetched %d headlines from %d feeds", len(out), len(resolved))
    return out


def pick_fresh_headline(
    conn: sqlite3.Connection,
    *,
    feeds: list[tuple[str, str]] | None = None,
    headlines: list[Headline] | None = None,
) -> Headline | None:
    """Return the first headline not already in `seen_headlines`. Marks it seen."""
    headlines = headlines if headlines is not None else fetch_headlines(feeds=feeds)
    seen = seen_headline_hashes(conn)
    for h in headlines:
        if h.hash not in seen:
            record_seen_headline(
                conn, headline_hash=h.hash, title=h.title, source=h.source, link=h.link
            )
            return h
    return None
