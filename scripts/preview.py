#!/usr/bin/env python3
"""
DEPRECATED: This module is deprecated. Use `content_engine.cli manual preview` instead.

Preview Mode for Content Engine.

Executes the Planner, generates the Content Brief, and generates every platform post.
Displays everything to the console.
NO PUBLISHING occurs.

Usage:
  BLOG_URL=https://afrigen.com.ng/blog/my-post python scripts/preview.py
"""

import os
import sys
import json
from dotenv import load_dotenv

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_root_dir, ".env"))
sys.path.insert(0, _root_dir)

from scripts.distribute import resolve_blog_post
from scripts.generate_content import generate_all

def main():
    blog_url = os.environ.get("BLOG_URL", "").strip()

    if not blog_url:
        print("ERROR: BLOG_URL is not set.", file=sys.stderr)
        print("Usage: BLOG_URL=https://afrigen.com.ng/blog/my-post python scripts/preview.py", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"[preview] PREVIEW MODE ACTIVATED")
    print(f"{'='*60}")

    post = resolve_blog_post(blog_url)
    if not post:
        print(f"Could not resolve blog post from {blog_url}, using mock data for preview.")
        post = {
            "slug": "mock-post",
            "title": "A Mock Post for Preview",
            "description": "This is a mock description for previewing the engine.",
            "body": "<p>This is a mock body. It talks about AI video generation in Africa.</p>",
            "url": blog_url
        }

    print(f"\nResolved Blog: {post['title']}")
    print(f"URL: {post['url']}")
    
    print(f"\n{'='*60}")
    print(f"[preview] GENERATING CONTENT")
    print(f"{'='*60}")
    
    content_results = generate_all(post)
    
    print(f"\n{'='*60}")
    print(f"[preview] GENERATED CONTENT DISPLAY")
    print(f"{'='*60}")
    
    for cr in content_results:
        platform = cr.get("platform", "Unknown")
        print(f"\n--- {platform.upper()} ---")
        if "error" in cr:
            print(f"❌ Error: {cr['error']}")
        else:
            print("✅ Generated Content:")
            print(cr.get("content", ""))
            
            extra = {k: v for k, v in cr.items() if k not in ("platform", "content")}
            if extra:
                print("\nExtra Fields:")
                for k, v in extra.items():
                    print(f"  {k}: {v}")
    
    print(f"\n{'='*60}")
    print(f"[preview] PREVIEW COMPLETE. NO PUBLISHING OCCURRED.")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
