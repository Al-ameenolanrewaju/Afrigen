#!/usr/bin/env python3
"""
DEPRECATED: This module is deprecated. Use `content_engine.cli manual dry_run` or `publish_blog` instead.

Content distribution orchestrator for Afrigen blog posts.

Triggered by:
  1. GitHub Actions workflow_dispatch (manual, blog URL input)
  2. GitHub Actions repository_dispatch (webhook from Flask admin publish)

Flow:
  1. Resolve blog post content from URL
  2. Generate platform-specific content via Groq (scripts/generate_content.py)
  3. Post to each platform independently (one failure doesn't stop others)
  4. Ping Google Indexing API
  5. Send admin notification via Telegram with results

Usage (local test):
  BLOG_URL=https://afrigen.com.ng/blog/my-post GROQ_API_KEY=... python scripts/distribute.py
"""

import os
import sys
import re
import json
import traceback
from datetime import datetime, timezone
from dotenv import load_dotenv

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_root_dir, ".env"))

# ---------------------------------------------------------------------------
# Resolve blog post content
# ---------------------------------------------------------------------------

sys.path.insert(0, _root_dir)
from constants import SITE_URL


def resolve_blog_post(blog_url: str) -> dict | None:
    """Fetch a blog post's data from afrigen.com.ng.

    Tries:
      1. JSON API endpoint: GET /api/v1/blog/<slug> (returns structured data)
      2. Fallback: scrape the HTML blog page

    Returns dict with {slug, title, description, body} or None on failure.
    """
    import requests

    blog_url = blog_url.strip().rstrip("/")
    print(f"[distribute] resolving blog post: {blog_url}")

    # Extract slug from URL
    # Supports: /blog/slug, /blog/slug/, ?...
    match = re.search(r"/blog/([^/?#]+)", blog_url)
    if not match:
        print(f"[distribute] ❌ could not extract slug from URL: {blog_url}")
        return None

    slug = match.group(1)

    # Try the JSON API first — this is the clean fast path.
    api_url = f"{SITE_URL}/api/v1/blog/{slug}"
    try:
        resp = requests.get(api_url, timeout=15, headers={"User-Agent": "Afrigen-Distributor/1.0"})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok") and data.get("post"):
                post = data["post"]
                print(f"[distribute] ✅ resolved via API: \"{post.get('title', '')}\"")
                return {
                    "slug": post.get("slug", slug),
                    "title": post.get("title", ""),
                    "description": post.get("description", ""),
                    "body": post.get("body", ""),
                    "tag": post.get("tag", ""),
                    "url": f"{SITE_URL}/blog/{slug}",
                }
        print(f"[distribute] API returned {resp.status_code}, trying HTML fallback...")
    except Exception as e:
        print(f"[distribute] API fetch failed: {e}, trying HTML fallback...")

    # Fallback: parse the rendered HTML
    try:
        resp = requests.get(blog_url, timeout=15, headers={"User-Agent": "Afrigen-Distributor/1.0"})
        resp.raise_for_status()
        html = resp.text

        # Extract title from <title> tag
        title_match = re.search(r"<title>(.*?)(?:\s*\|\s*Afrigen)?</title>", html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else slug.replace("-", " ").title()

        # Extract description from meta description
        desc_match = re.search(
            r'<meta\s+name="description"\s+content="([^"]*)"',
            html, re.IGNORECASE,
        )
        description = desc_match.group(1).strip() if desc_match else ""

        # Extract the article body — look for a div containing the blog content.
        # On afrigen.com.ng, the body is inside div.card > div.card-body or similar.
        body = ""
        body_match = re.search(
            r'<div[^>]*class="[^"]*card-body[^"]*"[^>]*>(.*?)</div>\s*(?:</div>\s*){0,2}(?:<div|$)',
            html, re.DOTALL | re.IGNORECASE,
        )
        if body_match:
            body = body_match.group(1).strip()
        else:
            # Broader fallback: grab everything between the first <p> and last </p>
            # inside the main content area
            main_match = re.search(
                r'<main[^>]*>(.*?)</main>',
                html, re.DOTALL | re.IGNORECASE,
            )
            if main_match:
                body = main_match.group(1).strip()

        print(f"[distribute] ✅ resolved via HTML: \"{title}\"")
        return {
            "slug": slug,
            "title": title,
            "description": description,
            "body": body,
            "tag": "",
            "url": f"{SITE_URL}/blog/{slug}",
        }

    except Exception as e:
        print(f"[distribute] ❌ HTML fallback also failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Per-platform dispatch (active platforms only)
# ---------------------------------------------------------------------------

def _post_to_platform(platform: str, content: dict, post: dict) -> dict:
    """Publish already-generated content to a single ACTIVE platform.

    Active platforms: telegram, linkedin, devto, hashnode. Each publisher returns
    {ok, error, ...} and skips gracefully when its credentials are missing."""
    canonical = content.get("canonicalUrl", f"{SITE_URL}/blog/{post['slug']}")

    if platform == "telegram":
        from platforms.telegram import post_to_channel
        return post_to_channel(content.get("content", ""))

    elif platform == "linkedin":
        from platforms.linkedin import post_article
        return post_article(content.get("content", ""))

    elif platform == "devto":
        from platforms.devto import publish_article
        return publish_article(
            title=content.get("title", post["title"]),
            content=content.get("content", ""),
            tags=content.get("tags", []),
            canonical_url=canonical,
            description=content.get("description", ""),
        )

    elif platform == "hashnode":
        from platforms.hashnode import publish_article
        return publish_article(
            title=content.get("title", post["title"]),
            content=content.get("content", ""),
            tags=content.get("tags", []),
            canonical_url=canonical,
            subtitle=content.get("subtitle", ""),
        )

    elif platform == "pinterest":
        from platforms.pinterest import create_pin
        return create_pin(
            title=content.get("title", post["title"]),
            description=content.get("description", ""),
            link=content.get("link", canonical),
            image_url=content.get("image_url", ""),
            image_title=content.get("image_title", post.get("title", "")),
        )

    return {"ok": False, "error": f"Platform '{platform}' is not active"}


# ---------------------------------------------------------------------------
# Main distribution pipeline
# ---------------------------------------------------------------------------

def distribute(blog_url: str) -> dict:
    """Run the full distribution pipeline.

    Returns a dict with per-platform results and overall status.
    """
    results = {
        "blog_url": blog_url,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "platforms": {},
    }

    if os.environ.get("DRY_RUN") == "true":
        print(f"\n{'='*60}")
        print(f"[distribute] 🚧 DRY RUN MODE ACTIVATED 🚧")
        print(f"{'='*60}")
        results["dry_run"] = True

    # 1. Resolve blog content
    print(f"\n{'='*60}")
    print(f"[distribute] STEP 1: Resolve blog content")
    print(f"{'='*60}")

    post = resolve_blog_post(blog_url)
    if not post:
        results["error"] = f"Could not resolve blog post from {blog_url}"
        return results

    results["post_title"] = post["title"]
    results["post_slug"] = post["slug"]

    # 2. Generate platform content
    print(f"\n{'='*60}")
    print(f"[distribute] STEP 2: Generate platform content via Groq")
    print(f"{'='*60}")

    from generate_content import generate_all

    content_results = generate_all(post)
    content_map = {}
    for cr in content_results:
        if "error" in cr:
            print(f"[distribute] ⚠️ skipping {cr['platform']} — generation failed: {cr['error']}")
        content_map[cr["platform"]] = cr

    # 3. Post to each platform independently.
    # One failed platform NEVER stops the others — each is wrapped in try/except
    # and missing credentials are reported by the publisher as a graceful skip.
    print(f"\n{'='*60}")
    print(f"[distribute] STEP 3: Distribute to platforms")
    print(f"{'='*60}")

    from generate_content import ACTIVE_PLATFORMS

    for platform in ACTIVE_PLATFORMS:
        content = content_map.get(platform)
        print(f"\n--- {platform} ---")

        # Generation failed earlier — record and move on.
        if not content or "error" in (content or {}):
            err = (content or {}).get("error", "Generation failed")
            results["platforms"][platform] = {"ok": False, "error": err}
            print(f"[distribute] ❌ {platform}: {err}")
            continue

        try:
            pr = _post_to_platform(platform, content, post)
            results["platforms"][platform] = pr
            if pr.get("ok"):
                detail = pr.get("post_url") or pr.get("channel_link") or "posted"
                print(f"[distribute] ✅ {platform}: {detail}")
            else:
                print(f"[distribute] ❌ {platform}: {pr.get('error')}")
        except Exception as e:
            traceback.print_exc()
            results["platforms"][platform] = {"ok": False, "error": str(e)}
            print(f"[distribute] ❌ {platform} exception: {e}")

    # 4. Google Indexing
    print(f"\n{'='*60}")
    print(f"[distribute] STEP 4: Google Indexing API")
    print(f"{'='*60}")
    try:
        from platforms.google_indexing import notify_url

        g_result = notify_url(post["url"])
        results["platforms"]["google_indexing"] = g_result
        if g_result.get("ok"):
            print(f"[distribute] ✅ Google Indexing: notified")
        else:
            print(f"[distribute] ⚠️ Google Indexing: {g_result.get('error')}")
    except Exception as e:
        traceback.print_exc()
        results["platforms"]["google_indexing"] = {"ok": False, "error": str(e)}

    # 5. Admin notification
    print(f"\n{'='*60}")
    print(f"[distribute] STEP 5: Admin notification")
    print(f"{'='*60}")
    try:
        from platforms.telegram import notify_admin

        report = _build_report(results)
        notify_result = notify_admin(report)
        results["admin_notified"] = notify_result.get("ok", False)
        if results["admin_notified"]:
            print("[distribute] ✅ Admin notified via Telegram")
        else:
            print(f"[distribute] ⚠️ Admin notification failed: {notify_result.get('error')}")
    except Exception as e:
        traceback.print_exc()
        results["admin_notified"] = False

    # Summary
    print(f"\n{'='*60}")
    print(f"[distribute] DISTRIBUTION COMPLETE")
    print(f"{'='*60}")
    success_count = sum(
        1 for p in results["platforms"].values() if p.get("ok")
    )
    total = len(results["platforms"])
    print(f"  {success_count}/{total} platforms succeeded")
    for platform, pr in results["platforms"].items():
        icon = "✅" if pr.get("ok") else "❌"
        detail = pr.get("post_url") or pr.get("urls", [None])[0] or pr.get("channel_link") or pr.get("error", "—")
        print(f"  {icon} {platform}: {detail}")

    return results


# ---------------------------------------------------------------------------
# Admin report builder
# ---------------------------------------------------------------------------

def _build_report(results: dict) -> str:
    """Build a human-readable Telegram message for the admin."""
    from generate_content import SITE_URL

    lines = [
        "\U0001f4e2 <b>Afrigen Distribution Report</b>\n",
        f"\U0001f4dd <b>{results.get('post_title', 'Blog Post')}</b>",
        f"\U0001f517 {results.get('blog_url', '')}\n",
        "<b>Results:</b>",
    ]

    for platform, pr in results.get("platforms", {}).items():
        icon = "✅" if pr.get("ok") else "❌"
        if pr.get("ok"):
            url = (
                pr.get("post_url")
                or (pr.get("urls") or [None])[0]
                or pr.get("channel_link")
                or ""
            )
            lines.append(f"{icon} <b>{platform}</b>: <a href=\"{url}\">{url}</a>" if url else f"{icon} <b>{platform}</b>: posted")
        else:
            error = (pr.get("error") or "unknown error")[:100]
            lines.append(f"{icon} <b>{platform}</b>: {error}")

    lines.append(f"\n\U0001f4ca <b>{SITE_URL}/blog/{results.get('post_slug', '')}</b>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    blog_url = os.environ.get("BLOG_URL", "").strip()

    if not blog_url:
        print("ERROR: BLOG_URL is not set.", file=sys.stderr)
        print("Usage: BLOG_URL=https://afrigen.com.ng/blog/my-post python scripts/distribute.py",
              file=sys.stderr)
        sys.exit(1)

    results = distribute(blog_url)

    # Write results to a JSON file so the GitHub Action can upload it as an
    # artifact (useful for debugging).
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if output_path:
        with open(output_path, "a") as f:
            f.write(f"success_count={sum(1 for p in results['platforms'].values() if p.get('ok'))}\n")
            f.write(f"total_platforms={len(results['platforms'])}\n")

    # Write full results to a file for artifact upload
    with open("distribution-results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print("\n[distribute] Full results written to distribution-results.json")

    # Exit with error code if all platforms failed
    all_failed = all(
        not pr.get("ok", False) for pr in results["platforms"].values()
    )
    if all_failed:
        print("\n[distribute] ❌ ALL platforms failed. Exiting with error.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
