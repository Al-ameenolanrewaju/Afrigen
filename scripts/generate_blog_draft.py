#!/usr/bin/env python3
"""
Generate ONE blog draft for Afrigen and save it to the database as status='draft'.

This is a thin wrapper for MANUAL / local runs. The actual generation logic lives
in services.blog.run_daily_draft_generation, so this script and the daily
scheduler in app.py share one code path. In production the draft is generated
in-process by that scheduler (mirroring the weekly newsletter) — no external cron.

It NEVER publishes — drafts are reviewed and approved by an admin at /admin/blog.

Run locally to test:  python scripts/generate_blog_draft.py
Requires env vars:    GROQ_API_KEY, DATABASE_URL
"""
import os
import sys

# Make repo-root modules (config, models, services) importable no matter the CWD.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask

from config import Config
from models import db


def make_app():
    """Minimal app context purely for DB access — does NOT import app.py, so the
    scheduler, Telegram bot and web routes never spin up in this process."""
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def main():
    app = make_app()
    with app.app_context():
        # Ensure the table exists even if this runs before the web service migrates.
        db.create_all()

        from services.blog import run_daily_draft_generation

        try:
            run_daily_draft_generation()
        except Exception as e:
            print(f"[blog-draft] ❌ GENERATION FAILED: {e}", flush=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
