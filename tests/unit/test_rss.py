from __future__ import annotations

import sqlite3

from agent.db.store import seen_headline_hashes
from agent.sources import rss
from agent.sources.rss import Headline, pick_fresh_headline

RSS_SAMPLE = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Sample</title>
    <item>
      <title>Anthropic releases Claude 5</title>
      <description>Big improvements in reasoning.</description>
      <link>https://example.com/a</link>
    </item>
    <item>
      <title>OpenAI launches new model</title>
      <description>It is bigger.</description>
      <link>https://example.com/b</link>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>HF blog post about new dataset</title>
    <link href="https://example.com/c"/>
    <summary>Dataset details.</summary>
  </entry>
</feed>
"""


def test_parse_rss_extracts_items() -> None:
    headlines = rss._parse_rss(RSS_SAMPLE, "Sample")
    assert len(headlines) == 2
    assert headlines[0].title.startswith("Anthropic")
    assert headlines[0].source == "Sample"
    assert headlines[0].link == "https://example.com/a"


def test_parse_atom_extracts_entries() -> None:
    headlines = rss._parse_rss(ATOM_SAMPLE, "HF")
    assert len(headlines) == 1
    assert headlines[0].title.startswith("HF blog")
    assert headlines[0].link == "https://example.com/c"


def test_parse_malformed_returns_empty() -> None:
    assert rss._parse_rss(b"<<<not xml>>>", "Broken") == []


def test_headline_hash_is_stable() -> None:
    a = Headline(title="Same Title", summary="x", link="y", source="z")
    b = Headline(title="same title", summary="x2", link="y2", source="z2")
    assert a.hash == b.hash  # case + summary insensitive


def test_pick_fresh_headline_dedups(tmp_db: sqlite3.Connection) -> None:
    h1 = Headline(title="A", summary="", link="", source="src")
    h2 = Headline(title="B", summary="", link="", source="src")

    first = pick_fresh_headline(tmp_db, headlines=[h1, h2])
    assert first is not None
    assert first.title == "A"
    assert h1.hash in seen_headline_hashes(tmp_db)

    second = pick_fresh_headline(tmp_db, headlines=[h1, h2])
    assert second is not None
    assert second.title == "B"

    third = pick_fresh_headline(tmp_db, headlines=[h1, h2])
    assert third is None  # both seen


def test_pick_fresh_with_no_headlines(tmp_db: sqlite3.Connection) -> None:
    assert pick_fresh_headline(tmp_db, headlines=[]) is None
