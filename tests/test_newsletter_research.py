from datetime import datetime, timezone
from unittest.mock import Mock

from services.newsletter_research import collect_newsletter_research


def test_collect_newsletter_research_parses_recent_rss_and_deduplicates():
    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    xml = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>New open model release</title>
        <link>https://publisher.example/news/model</link>
        <description><![CDATA[<p>A useful model update for creators.</p>]]></description>
        <pubDate>Tue, 17 Nov 2026 10:00:00 GMT</pubDate>
      </item>
      <item>
        <title>Old announcement</title>
        <link>https://publisher.example/news/old</link>
        <description>Too old to include.</description>
        <pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    response = Mock()
    response.content = xml
    response.raise_for_status = Mock()
    session = Mock()
    session.get.return_value = response
    feeds = [
        {"publisher": "Publisher", "url": "https://publisher.example/feed", "tier": 1},
        {"publisher": "Publisher mirror", "url": "https://publisher.example/feed2", "tier": 2},
    ]

    items = collect_newsletter_research(now=now, feeds=feeds, session=session)

    assert len(items) == 1
    assert items[0]["title"] == "New open model release"
    assert items[0]["publisher"] == "Publisher"
    assert items[0]["summary"] == "A useful model update for creators."
    assert items[0]["url"] == "https://publisher.example/news/model"
    assert items[0]["published_at"] == "2026-11-17T10:00:00+00:00"
    assert "source_tier" not in items[0]


def test_collect_newsletter_research_parses_atom_and_ignores_bad_feed():
    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    atom = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Research breakthrough</title>
        <link href="https://lab.example/research" rel="alternate" />
        <summary>New research details.</summary>
        <updated>2026-11-17T09:00:00Z</updated>
      </entry>
    </feed>"""
    response = Mock()
    response.content = atom
    response.raise_for_status = Mock()
    session = Mock()
    session.get.side_effect = [response, RuntimeError("feed unavailable")]
    feeds = [
        {"publisher": "Research Lab", "url": "https://lab.example/feed", "tier": 1},
        {"publisher": "Unavailable", "url": "https://bad.example/feed", "tier": 2},
    ]

    items = collect_newsletter_research(now=now, feeds=feeds, session=session)

    assert len(items) == 1
    assert items[0]["title"] == "Research breakthrough"
    assert items[0]["url"] == "https://lab.example/research"


def test_collect_newsletter_research_rejects_non_https_article_links():
    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    xml = b"""<rss><channel><item>
      <title>Unsafe link</title><link>http://example.com/story</link>
      <description>Not accepted.</description>
      <pubDate>Tue, 17 Nov 2026 10:00:00 GMT</pubDate>
    </item></channel></rss>"""
    response = Mock()
    response.content = xml
    response.raise_for_status = Mock()
    session = Mock()
    session.get.return_value = response

    items = collect_newsletter_research(
        now=now,
        feeds=[{"publisher": "Example", "url": "https://example.com/feed", "tier": 1}],
        session=session,
    )

    assert items == []
