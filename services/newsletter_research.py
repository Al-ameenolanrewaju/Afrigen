"""Curated RSS research for the daily editorial newsletter.

Only fixed, reviewed feed URLs are fetched. Feed content is treated as untrusted
source material; the writer receives short excerpts and canonical article links.
"""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Primary sources are preferred for announcements; established newsrooms add
# independent reporting and context. Keep this list deliberately curated.
NEWSLETTER_RSS_FEEDS = (
    {"publisher": "OpenAI", "url": "https://openai.com/news/rss.xml", "tier": 1, "source_type": "primary"},
    {"publisher": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "tier": 1, "source_type": "primary"},
    {"publisher": "Google AI", "url": "https://blog.google/technology/ai/rss/", "tier": 1, "source_type": "primary"},
    {"publisher": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml", "tier": 1, "source_type": "primary"},
    {"publisher": "MIT Technology Review", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed", "tier": 2, "source_type": "independent"},
    {"publisher": "TechCrunch", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "tier": 2, "source_type": "independent"},
    {"publisher": "The Verge", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "tier": 2, "source_type": "independent"},
    {"publisher": "Ars Technica", "url": "https://arstechnica.com/ai/feed/", "tier": 2, "source_type": "independent"},
    {"publisher": "Simon Willison", "url": "https://simonwillison.net/atom/everything/", "tier": 2, "source_type": "independent"},
)

REQUEST_TIMEOUT = (3.05, 8)
MAX_FEED_BYTES = 2_000_000
MAX_ITEMS_PER_FEED = 8
MAX_AGE = timedelta(hours=72)
MAX_RESEARCH_ITEMS = 8
USER_AGENT = "CreatorIntelligenceBrief/1.0 (+newsletter research; RSS reader)"


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = (data or "").strip()
        if value:
            self.parts.append(value)


def _plain_text(value, limit=700):
    parser = _TextExtractor()
    try:
        parser.feed(unescape(value or ""))
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _parse_date(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _child_text(element, names):
    for child in list(element):
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names:
            if local == "link":
                href = child.attrib.get("href")
                if href:
                    return href.strip()
            return "".join(child.itertext()).strip()
    return ""


def _entry_link(entry):
    for child in list(entry):
        if child.tag.rsplit("}", 1)[-1].lower() == "link":
            href = child.attrib.get("href")
            if href and child.attrib.get("rel", "alternate") in ("alternate", ""):
                return href.strip()
            if child.text and child.text.strip():
                return child.text.strip()
    return _child_text(entry, {"link"})


def _parse_feed(xml_bytes, source, now):
    root = ET.fromstring(xml_bytes)
    entries = [
        node for node in root.iter()
        if node.tag.rsplit("}", 1)[-1].lower() in ("item", "entry")
    ]
    results = []
    for entry in entries[:MAX_ITEMS_PER_FEED]:
        title = _plain_text(_child_text(entry, {"title"}), 240)
        link = _entry_link(entry)
        summary = _plain_text(
            _child_text(entry, {"description", "summary", "content", "encoded"}), 700
        )
        published_raw = _child_text(
            entry, {"pubdate", "published", "updated", "date", "issued"}
        )
        published = _parse_date(published_raw)
        if not title or not link or not published:
            continue
        parsed_url = urlparse(link)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            continue
        if published < now - MAX_AGE or published > now + timedelta(minutes=5):
            continue
        results.append({
            "title": title,
            "publisher": source["publisher"],
            "published_at": published.isoformat(),
            "url": link,
            "summary": summary,
            "source_tier": source["tier"],
            "source_type": source.get("source_type", "unknown"),
        })
    return results


# Headline grouping is a discovery signal only. It does not establish that the
# underlying claims are true or that publishers used independent reporting.
_TITLE_STOPWORDS = {
    "about", "after", "amid", "and", "are", "announces", "been", "for",
    "from", "has", "have", "into", "its", "new", "over", "says", "that",
    "the", "their", "this", "with", "will", "your",
}


def _headline_tokens(title):
    words = re.findall(r"[a-z0-9]{3,}", (title or "").lower())
    return {word for word in words if word not in _TITLE_STOPWORDS}


def _headline_similarity(left, right):
    a, b = _headline_tokens(left), _headline_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def annotate_story_coverage(items, similarity_threshold=0.42):
    """Flag likely cross-publisher coverage; never label it fact-verified.

    Publisher labels are a rough signal: RSS alone cannot rule out syndication,
    common press releases, shared ownership, or shared original sourcing.
    """
    groups = []
    for item in items:
        match = None
        for group in groups:
            if any(
                existing["publisher"] != item["publisher"]
                and _headline_similarity(existing["title"], item["title"]) >= similarity_threshold
                for existing in group
            ):
                match = group
                break
        if match is None:
            groups.append([item])
        else:
            match.append(item)

    annotated = []
    for group in groups:
        publishers = list(dict.fromkeys(entry["publisher"] for entry in group))
        source_types = {entry.get("source_type", "unknown") for entry in group}
        if len(publishers) > 1:
            status = "multiple_outlets"
        elif source_types == {"primary"}:
            status = "primary_source_only"
        else:
            status = "single_source"
        for item in group:
            annotated.append({
                **item,
                "coverage_status": status,
                "coverage_count": len(publishers),
                "coverage_publishers": publishers,
                "coverage_note": (
                    "Related headlines appeared across multiple outlets; this is not proof "
                    "of independent corroboration or factual accuracy."
                    if len(publishers) > 1 else
                    "Only one publisher was found in this feed sample; this does not mean the report is false."
                ),
            })
    return annotated


def collect_newsletter_research(now=None, feeds=None, session=None):
    """Fetch, validate, deduplicate and rank recent items from curated RSS feeds.

    Returns at most eight source records. Individual feed failures are logged and
    isolated so one publisher outage never blocks newsletter generation.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    feeds = feeds if feeds is not None else NEWSLETTER_RSS_FEEDS
    http = session or requests
    items, seen = [], set()

    for source in feeds:
        try:
            response = http.get(
                source["url"],
                headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            content = response.content
            if len(content) > MAX_FEED_BYTES:
                logger.warning("Skipping oversized newsletter feed: %s", source["publisher"])
                continue
            for item in _parse_feed(content, source, now):
                key = item["url"].split("#", 1)[0].rstrip("/")
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
        except Exception as exc:
            logger.warning("Newsletter research feed failed (%s): %s", source["publisher"], exc)

    items.sort(key=lambda item: (item["source_tier"], item["published_at"]), reverse=False)
    # Keep the freshest material overall while giving primary sources a modest
    # tie-break advantage, rather than allowing one busy feed to dominate.
    items.sort(
        key=lambda item: (
            datetime.fromisoformat(item["published_at"]),
            -item["source_tier"],
        ),
        reverse=True,
    )
    selected = [
        {key: value for key, value in item.items() if key != "source_tier"}
        for item in items[:MAX_RESEARCH_ITEMS]
    ]
    return annotate_story_coverage(selected)
