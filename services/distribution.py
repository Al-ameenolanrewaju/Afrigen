"""
Content distribution service — callable from the Flask admin panel.

Triggers distribution for a published blog post: generates platform-specific
content via Groq, posts to each platform independently, stores results in the
database, and notifies the admin via Telegram.

Mirrors scripts/distribute.py but runs inside the Flask process in a background
thread so the admin UI stays responsive.
"""

import os
import sys
import json
import threading
import traceback
from datetime import datetime, timezone

# Make scripts/ importable so we can reuse generate_content and the platform
# modules without duplicating them.
_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from generate_content import generate_all, SITE_URL
from models import db, BlogPost, DistributionRun, DistributionResult


# ---------------------------------------------------------------------------
# Public API — called from admin routes
# ---------------------------------------------------------------------------

def trigger_distribution(post_id: int) -> int:
    """Start a distribution run for a published blog post in a background thread.

    Returns the DistributionRun id immediately. The admin UI polls for updates.
    If the post is not published, raises ValueError.
    """
    post = db.session.get(BlogPost, post_id)
    if not post:
        raise ValueError(f"Blog post {post_id} not found.")
    if post.status != "published":
        raise ValueError(f"Blog post {post_id} is not published (status={post.status}).")

    run = DistributionRun(
        blog_post_id=post.id,
        status="running",
        total_platforms=0,
        success_count=0,
        fail_count=0,
    )
    db.session.add(run)
    db.session.commit()

    run_id = run.id

    # Fire in background thread — the admin gets their response immediately.
    threading.Thread(target=_execute_run, args=(run_id,), daemon=True).start()

    return run_id


def retry_platform(run_id: int, platform: str) -> bool:
    """Retry a single failed platform within an existing run.

    Re-generates the content for that platform and posts it. Updates the
    existing DistributionResult row.
    """
    run = db.session.get(DistributionRun, run_id)
    if not run:
        raise ValueError(f"Distribution run {run_id} not found.")

    existing = DistributionResult.query.filter_by(run_id=run_id, platform=platform).first()
    if not existing:
        raise ValueError(f"No result for platform '{platform}' in run {run_id}.")

    post = run.blog_post
    if not post:
        raise ValueError("Blog post not found for this run.")

    # Re-generate content for this specific platform. _GENERATORS includes the
    # active platforms (telegram, linkedin, devto, hashnode); disabled ones stay
    # mapped there too so a historical row can still be retried if re-enabled.
    from generate_content import _GENERATORS

    gen_fn = _GENERATORS.get(platform)
    if not gen_fn:
        raise ValueError(f"Unknown platform: {platform}")

    post_dict = {
        "slug": post.slug,
        "title": post.title,
        "description": post.description,
        "body": post.body,
    }

    try:
        content = gen_fn(post_dict)
        result = _post_to_platform(platform, content, post_dict)
        existing.ok = result["ok"]
        existing.error = result.get("error") if not result["ok"] else None
        existing.post_url = result.get("post_url") or (
            result.get("urls", [None])[0] if result.get("urls") else None
        )
        existing.extra = json.dumps(result, ensure_ascii=False, default=str)

        # Recalculate run counts from all results
        run.success_count = sum(1 for r in run.results if r.ok)
        run.fail_count = sum(1 for r in run.results if not r.ok)
        db.session.commit()
        return result["ok"]
    except Exception as e:
        existing.ok = False
        existing.error = str(e)[:500]
        run.fail_count = sum(1 for r in run.results if not r.ok)
        run.success_count = sum(1 for r in run.results if r.ok)
        db.session.commit()
        return False


def get_run(run_id: int) -> DistributionRun | None:
    """Get a distribution run with its results eagerly loaded."""
    return db.session.get(DistributionRun, run_id)


def get_latest_run_for_post(post_id: int) -> DistributionRun | None:
    """Get the most recent distribution run for a blog post."""
    return (
        DistributionRun.query
        .filter_by(blog_post_id=post_id)
        .order_by(DistributionRun.started_at.desc())
        .first()
    )


def get_all_runs(limit: int = 20) -> list[DistributionRun]:
    """Recent distribution runs, newest first."""
    return (
        DistributionRun.query
        .order_by(DistributionRun.started_at.desc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Internal execution
# ---------------------------------------------------------------------------

def _execute_run(run_id: int):
    """Run the full distribution pipeline in a background thread. Updates the
    DistributionRun row as it progresses so the admin UI can poll for live status.

    Creates a MINIMAL Flask app context — deliberately does NOT import app.py
    because that would re-initialize the scheduler, Telegram bot, blueprints,
    and all routes in the background thread."""
    from flask import Flask
    from config import Config

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    ctx = app.app_context()
    ctx.push()

    try:
        run = db.session.get(DistributionRun, run_id)
        if not run:
            print(f"[distribution] ❌ run {run_id} not found")
            return

        post = run.blog_post
        if not post:
            _fail_run(run, "Blog post not found")
            return

        post_dict = {
            "slug": post.slug,
            "title": post.title,
            "description": post.description,
            "body": post.body,
        }

        print(f"\n[distribution] ===== Run #{run.id}: \"{post.title}\" =====")

        # Step 1: Generate content for ALL platforms
        print(f"[distribution] Generating content via Groq ({len(post_dict['body'])} chars body)...")
        content_results = generate_all(post_dict)

        # Create pending result rows
        for cr in content_results:
            dr = DistributionResult(
                run_id=run.id,
                platform=cr["platform"],
                ok=False,
                error=cr.get("error"),
            )
            db.session.add(dr)
        db.session.commit()

        # Step 2: Post to each platform independently
        for cr in content_results:
            platform = cr["platform"]
            if "error" in cr:
                print(f"[distribution] ⚠️ {platform}: generation failed — {cr['error']}")
                continue

            result_row = DistributionResult.query.filter_by(
                run_id=run.id, platform=platform
            ).first()
            if not result_row:
                continue

            try:
                print(f"[distribution] Posting to {platform}...")
                result = _post_to_platform(platform, cr, post_dict)

                result_row.ok = result["ok"]
                result_row.error = result.get("error") if not result["ok"] else None
                result_row.post_url = result.get("post_url") or (
                    result.get("urls", [None])[0] if result.get("urls") else None
                )
                result_row.extra = json.dumps(result, ensure_ascii=False, default=str)

                db.session.commit()

                if result["ok"]:
                    print(f"[distribution] ✅ {platform}: {result_row.post_url or 'posted'}")
                else:
                    print(f"[distribution] ❌ {platform}: {result_row.error}")

            except Exception as e:
                traceback.print_exc()
                result_row.ok = False
                result_row.error = str(e)[:500]
                db.session.commit()
                print(f"[distribution] ❌ {platform} exception: {e}")

        # Step 3: Google Indexing
        print(f"[distribution] Pinging Google Indexing...")
        _ping_google(post_dict["slug"], run)

        # Step 4: Finalize run
        results = DistributionResult.query.filter_by(run_id=run.id).all()
        run.success_count = sum(1 for r in results if r.ok)
        run.fail_count = sum(1 for r in results if not r.ok)
        run.total_platforms = len(results)

        if run.success_count > 0:
            run.status = "completed"
        else:
            run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()

        print(
            f"[distribution] ===== Run #{run.id} {run.status}: "
            f"{run.success_count}/{run.total_platforms} succeeded ====="
        )

        # Step 5: Admin notification
        try:
            _notify_admin(run)
        except Exception as e:
            print(f"[distribution] ⚠️ Admin notification failed: {e}")

    except Exception as e:
        traceback.print_exc()
        try:
            run = db.session.get(DistributionRun, run_id)
            if run:
                _fail_run(run, f"Pipeline crashed: {e}")
        except Exception:
            pass
    finally:
        if ctx:
            ctx.pop()


def _post_to_platform(platform: str, content: dict, post: dict) -> dict:
    """Post generated content to a single platform. Returns result dict.

    Only the ACTIVE platforms (telegram, linkedin, devto, hashnode) are handled.
    Disabled platforms (twitter/facebook/instagram/medium) are no longer generated,
    so they should never reach here; if one does, it's reported, not crashed."""
    from generate_content import SITE_URL
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

    else:
        return {"ok": False, "error": f"Platform '{platform}' is not active"}


def _ping_google(slug: str, run: DistributionRun):
    """Ping Google Indexing API for the blog post URL."""
    try:
        from platforms.google_indexing import notify_url
        url = f"{SITE_URL}/blog/{slug}"
        result = notify_url(url)

        gr = DistributionResult(
            run_id=run.id,
            platform="google_indexing",
            ok=result.get("ok", False),
            error=result.get("error") if not result.get("ok") else None,
            extra=json.dumps(result, ensure_ascii=False, default=str),
        )
        db.session.add(gr)
        db.session.commit()
    except Exception as e:
        gr = DistributionResult(
            run_id=run.id,
            platform="google_indexing",
            ok=False,
            error=str(e)[:500],
        )
        db.session.add(gr)
        db.session.commit()


def _fail_run(run: DistributionRun, error: str):
    """Mark a run as failed with a top-level error."""
    run.status = "failed"
    run.finished_at = datetime.now(timezone.utc)
    run.fail_count = run.total_platforms or 1
    db.session.commit()
    print(f"[distribution] Run #{run.id} FAILED: {error}")


def _notify_admin(run: DistributionRun):
    """Send a distribution report to the admin via Telegram DM."""
    from platforms.telegram import notify_admin

    post = run.blog_post
    lines = [
        "\U0001f4e2 <b>Afrigen Distribution Report</b>\n",
        f"\U0001f4dd <b>{post.title}</b>" if post else "",
        f"\U0001f517 {SITE_URL}/blog/{post.slug}\n" if post else "",
        f"<b>Run #{run.id}</b> — {run.status.upper()} "
        f"({run.success_count}/{run.total_platforms} succeeded)\n",
        "<b>Results:</b>",
    ]

    for r in run.results:
        icon = "✅" if r.ok else "❌"
        if r.ok and r.post_url:
            lines.append(f'{icon} <b>{r.platform}</b>: <a href="{r.post_url}">{r.post_url}</a>')
        elif r.ok:
            lines.append(f'{icon} <b>{r.platform}</b>: posted')
        else:
            error = (r.error or "unknown error")[:100]
            lines.append(f'{icon} <b>{r.platform}</b>: {error}')

    report = "\n".join(lines)
    notify_admin(report)
