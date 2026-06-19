#!/usr/bin/env python3
"""
Generate ONE blog draft for Afrigen and save it to the database as status='draft'.

This is a standalone script run by a Render Cron Job (see render.yaml). It NEVER
publishes — drafts are reviewed and approved by an admin at /admin/blog.

It:
  1. Bootstraps a minimal Flask app context so it can reach the shared Postgres
     DB (the same one the web service uses) via DATABASE_URL.
  2. Reads every existing title/slug (draft AND published) so it never repeats.
  3. Pulls fresh real-world headlines from Google News RSS for specificity.
  4. Asks Groq (llama-3.3-70b-versatile) for one original 600-900 word post, with
     strict rules against generic/filler/"AI-sounding" content.
  5. Inserts the result as a draft and logs the outcome.

Run locally to test:  python scripts/generate_blog_draft.py
Requires env vars:    GROQ_API_KEY, DATABASE_URL
"""
import os
import sys
import json
import re
from datetime import datetime
from xml.etree import ElementTree

# Make repo-root modules (config, models, services) importable no matter the CWD.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from flask import Flask

from config import Config
from models import db


# Model is overridable, but defaults to the same Groq model the rest of the app uses.
BLOG_MODEL = os.environ.get("BLOG_MODEL", "llama-3.3-70b-versatile")

# Fresh headlines give the model concrete, current hooks to write around.
NEWS_QUERIES = [
    "AI video generation tools",
    "African content creators social media",
    "TikTok Instagram creators Nigeria",
]


def log(msg):
    print(f"[blog-draft {datetime.utcnow():%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def make_app():
    """Minimal app context purely for DB access — does NOT import app.py, so the
    scheduler, Telegram bot and web routes never spin up in the cron process."""
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def fetch_web_context(max_per_query=4, timeout=8):
    """Pull this week's real headlines from Google News RSS (free, no key).
    Returns a list of '- Headline (Source)' strings; [] on any failure."""
    headlines = []
    for query in NEWS_QUERIES:
        q = requests.utils.quote(f"{query} when:14d")
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
            for item in root.findall("./channel/item")[:max_per_query]:
                title = (item.findtext("title") or "").strip()
                src_el = item.find("source")
                source = (src_el.text or "").strip() if src_el is not None else ""
                if title:
                    headlines.append(f"- {title}" + (f" ({source})" if source else ""))
        except Exception as e:
            log(f"News fetch failed for '{query}': {e}")

    seen, deduped = set(), []
    for h in headlines:
        if h not in seen:
            seen.add(h)
            deduped.append(h)
    return deduped


def build_prompt(existing_titles, headlines):
    titles_block = "\n".join(f"- {t}" for t in existing_titles) or "(none yet)"
    headlines_block = "\n".join(headlines) if headlines else "(no fresh headlines available)"

    system = (
        "You are a senior content writer for Afrigen (tagline 'Africa Creates, AI "
        "Generates'), an African AI platform that turns text prompts into videos and "
        "images. You write for REAL Nigerian and African content creators, small "
        "business owners, and marketers who use AI video tools. You write like a "
        "knowledgeable local practitioner, not a generic blog mill."
    )

    user = f"""Write ONE original blog post for the Afrigen blog.

POSTS THAT ALREADY EXIST — do NOT repeat or closely overlap any of these topics; pick a clearly different, fresh angle:
{titles_block}

FRESH REAL-WORLD HEADLINES (for grounding and specificity — reference ideas/trends naturally, do not fabricate quotes):
{headlines_block}

HARD REQUIREMENTS:
- Length: 600 to 900 words in the body. Not shorter, not longer.
- Audience: Nigerian / African creators and small businesses using AI video tools. Write to them directly.
- Be CONCRETE. Use specific, real platforms by name (TikTok, Instagram Reels, YouTube Shorts, WhatsApp Status, Facebook). Use specific Nigerian/African places, scenarios, and content niches.
- Where money is relevant, use REAL figures in Naira (₦) — e.g. realistic costs of a videographer, data, a Pro subscription, ad spend. Use believable, current ranges, not round hand-wavy numbers.
- Give at least 2 concrete, worked examples (a real-sounding prompt, a real posting scenario, a before/after, a small calculation).
- Genuinely useful and actionable: a reader should be able to DO something after reading.

STRICTLY FORBIDDEN (this is content that previously got the site flagged by Google as low value):
- Generic filler, padding, or restating the obvious.
- Vague "AI-sounding" prose ("in today's fast-paced digital world", "unlock the power of", "the possibilities are endless", "game-changer", "in conclusion").
- Empty intros/outros that say nothing specific.
- Made-up statistics or fake quotes.

FORMAT — return ONLY a valid JSON object (no markdown fences, no commentary) with exactly these keys:
{{
  "title": "specific, non-clickbait title, max ~70 chars",
  "description": "one-sentence meta description for SEO, max 155 chars, specific",
  "tag": "one or two words categorizing the post (e.g. Prompting, Business, Platforms, Cost, Craft, Strategy)",
  "body_html": "the article body as inline-styled HTML"
}}

The body_html MUST use this exact styling to match the existing site design:
- Section subheadings: <h4 style="color: #F5A623;">Subheading</h4>
- Paragraphs: <p style="color: #C9D1D9; margin-bottom: 16px;">...</p>
- Lists: <ul style="color: #C9D1D9; margin-bottom: 16px;"><li>...</li></ul>
- Optional callout box: <div class="p-3 mb-3" style="background: #21262D; border-radius: 8px; border-left: 3px solid #F5A623;"><p style="color: #C9D1D9; margin: 0;">...</p></div>
- Use <strong> for emphasis. Do NOT include <html>, <head>, <body>, <h1>, <style>, or <script> tags. Start directly with an opening <p> intro paragraph (no title inside the body — the title is separate)."""

    return system, user


def strip_to_json(text):
    """The model is asked for raw JSON, but defensively strip ``` fences / stray prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    # Grab the outermost {...} if there's leading/trailing chatter.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return text


def word_count(html):
    return len(re.sub(r"<[^>]+>", " ", html).split())


def generate_post(existing_titles, headlines):
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")

    # Reuse the shared Groq client the rest of the app initialises.
    from services.claude import client

    system, user = build_prompt(existing_titles, headlines)

    log(f"Calling Groq ({BLOG_MODEL})...")
    resp = client.chat.completions.create(
        model=BLOG_MODEL,
        max_tokens=4000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = resp.choices[0].message.content or ""
    data = json.loads(strip_to_json(raw))

    title = (data.get("title") or "").strip()
    body = (data.get("body_html") or "").strip()
    if not title or not body:
        raise ValueError("Model response missing title or body_html")

    return {
        "title": title,
        "description": (data.get("description") or "").strip(),
        "tag": (data.get("tag") or "").strip(),
        "body": body,
    }


def main():
    app = make_app()
    with app.app_context():
        # Ensure the table exists even if the cron runs before the web service migrates.
        db.create_all()

        from services.blog import existing_titles_and_slugs, create_draft

        titles, _slugs = existing_titles_and_slugs()
        log(f"{len(titles)} existing posts found (drafts + published).")

        headlines = fetch_web_context()
        log(f"Pulled {len(headlines)} fresh headlines for grounding.")

        try:
            post = generate_post(titles, headlines)
        except Exception as e:
            log(f"❌ GENERATION FAILED: {e}")
            sys.exit(1)

        wc = word_count(post["body"])
        read_time = f"{max(1, round(wc / 200))} min read"
        log(f'Generated: "{post["title"]}" — {wc} words, tag={post["tag"]!r}')
        if not (550 <= wc <= 1000):
            log(f"⚠️  Word count {wc} is outside the 600-900 target — saving anyway for review.")

        draft = create_draft(
            title=post["title"],
            description=post["description"],
            body=post["body"],
            tag=post["tag"],
            read_time=read_time,
            auto_generated=True,
        )
        log(f'✅ SAVED DRAFT id={draft.id} slug="{draft.slug}" status={draft.status}.')
        log("Review and publish it at /admin/blog.")


if __name__ == "__main__":
    main()
