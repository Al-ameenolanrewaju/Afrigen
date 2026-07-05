import argparse
import sys
import os

# Ensure the root directory is in the path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(root_dir, ".env"))

from content_engine.pipeline import ContentPipeline

def main():
    parser = argparse.ArgumentParser(description="Content Engine CLI")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Execution mode")

    # 1. Automatic Mode
    auto_parser = subparsers.add_parser("automatic", help="Run automatic mode (daily cron)")

    # 2. Manual Mode
    manual_parser = subparsers.add_parser("manual", help="Run manual mode")
    manual_parser.add_argument("action", choices=["publish_today", "publish_blog", "preview", "dry_run"], help="Manual action to perform")
    manual_parser.add_argument("--url", help="Blog URL for publish_blog, preview, or dry_run")

    args = parser.parse_args()

    # We need an app context for database operations
    from flask import Flask
    from config import Config
    from models import db

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        if args.mode == "automatic":
            pipeline = ContentPipeline()
            pipeline.run_automatic()
            
        elif args.mode == "manual":
            if args.action == "publish_today":
                pipeline = ContentPipeline()
                pipeline.run_manual_publish_today()
                
            elif args.action == "publish_blog":
                if not args.url:
                    print("Error: --url is required for publish_blog")
                    sys.exit(1)
                pipeline = ContentPipeline()
                pipeline.run_manual_publish_blog(args.url)
                
            elif args.action == "preview":
                pipeline = ContentPipeline(preview=True)
                pipeline.run_manual_preview(args.url)
                
            elif args.action == "dry_run":
                pipeline = ContentPipeline(dry_run=True)
                pipeline.run_manual_dry_run(args.url)

if __name__ == "__main__":
    main()
