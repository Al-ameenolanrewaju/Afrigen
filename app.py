from flask import Flask
from flask_migrate import Migrate
from flask_login import LoginManager
from models import db, User, Generation, TelegramUser, SavedPrompt, Referral
from config import DevelopmentConfig
import os
from dotenv import load_dotenv
from flask_mail import Mail, Message
from routes.main import main
from routes.auth import auth
from routes.api import api
from authlib.integrations.flask_client import OAuth
from flask_apscheduler import APScheduler
from flask import render_template, redirect, url_for, request, jsonify
from telegram import Update
from telegram.ext import Application
import asyncio
import json
from flask import send_from_directory



load_dotenv()
app = Flask(__name__)

# Behind Render's proxy: trust X-Forwarded-* so url_for(_external=True) builds
# correct https://afrigen... URLs. Without this the fal webhook URL can come out
# with the wrong scheme/host and fal can't deliver the completion callback,
# leaving videos stuck "processing" forever.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config.from_object(DevelopmentConfig)
mail = Mail(app)
oauth = OAuth(app)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
telegram_app = None


db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = "auth.login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@scheduler.task('cron', id='reset_monthly_limits', day=1, hour=0)
def reset_monthly_limits():
    with app.app_context():
        from models import User

        free_users = User.query.filter_by(plan='free').all()

        for user in free_users:
            # Reset the free-tier monthly usage limits.
            user.monthly_videos_used = 0
            user.monthly_images_used = 0
            if user.credits < 10:
                user.credits = 10

        db.session.commit()

        print("✅ Monthly limits reset for free users!")


@scheduler.task('interval', id='fail_stuck_generations', minutes=5)
def fail_stuck_generations():
    """Rescue videos orphaned in 'processing'.

    Text-to-video is async: a row is created status='processing' and only flipped
    to completed/failed by the fal webhook. If that webhook never arrives (delivery
    failure, provider hiccup), the row is stuck forever and the user sees a
    permanent spinner. Every 5 minutes, mark any video still 'processing' after
    15 minutes as 'failed', and refund the free-tier monthly video count since the
    user got nothing (Pro credits are only charged on success, so there's nothing
    to refund there)."""
    from datetime import datetime, timedelta
    with app.app_context():
        from models import db, Generation, User
        cutoff = datetime.utcnow() - timedelta(minutes=15)
        stuck = Generation.query.filter(
            Generation.status == 'processing',
            Generation.created_at < cutoff,
        ).all()
        if not stuck:
            return
        for gen in stuck:
            gen.status = 'failed'
            user = db.session.get(User, gen.user_id)
            if user and user.plan == 'free' and (user.monthly_videos_used or 0) > 0:
                user.monthly_videos_used -= 1
        db.session.commit()
        print(f"⏱️ Failed {len(stuck)} stuck generation(s) past the 15-min timeout.")


@scheduler.task('cron', id='generate_weekly_newsletter', day_of_week='sat', hour=9)
def generate_weekly_newsletter():
    """Saturday 9am: build this week's draft so the admin can review it."""
    with app.app_context():
        try:
            from services.newsletter import run_weekly_generation
            run_weekly_generation()
        except Exception as e:
            print(f"Weekly newsletter generation failed: {e}")


@scheduler.task('cron', id='send_weekly_newsletter', day_of_week='mon', hour=9)
def send_weekly_newsletter():
    """Monday 9am: send the current draft to all users + waitlist."""
    with app.app_context():
        try:
            from services.newsletter import run_weekly_send
            run_weekly_send()
        except Exception as e:
            print(f"Weekly newsletter send failed: {e}")


@scheduler.task('cron', id='generate_daily_blog_draft', hour=7)
def generate_daily_blog_draft():
    """7am daily: generate ONE blog draft for the admin to review at /admin/blog.
    It never publishes itself. Runs in-process on the always-on web service, so
    it costs nothing extra (no paid Render cron)."""
    with app.app_context():
        try:
            from services.blog import run_daily_draft_generation
            run_daily_draft_generation()
        except Exception as e:
            print(f"Daily blog draft generation failed: {e}")

import logging
from logging.handlers import RotatingFileHandler

# Setup logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# File handler - rotates at 10MB, keeps 10 backups
file_handler = RotatingFileHandler(
    'logs/afrigen.log',
    maxBytes=10240000,  # 10MB
    backupCount=10
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s %(message)s'
))
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)

logger.info('Afrigen startup!')

app.register_blueprint(main)
app.register_blueprint(auth, url_prefix='/auth')
app.register_blueprint(api, url_prefix='/api/v1')

from constants import (
    FACEBOOK_URL, TWITTER_URL, INSTAGRAM_URL, LINKEDIN_URL, TELEGRAM_URL
)

@app.context_processor
def inject_socials():
    return dict(
        FACEBOOK_URL=FACEBOOK_URL,
        TWITTER_URL=TWITTER_URL,
        INSTAGRAM_URL=INSTAGRAM_URL,
        LINKEDIN_URL=LINKEDIN_URL,
        TELEGRAM_URL=TELEGRAM_URL
    )

@app.errorhandler(404)
def page_not_found(e):
    return render_template("errors/404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("errors/500.html"), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403


@app.route('/set-webhook')
def set_webhook():
    """Set Telegram webhook"""
    import requests as req

    webhook_url = f"https://afrigen.onrender.com/webhook/{TELEGRAM_TOKEN}"

    response = req.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
        json={"url": webhook_url}
    )

    result = response.json()
    print(f"Webhook set: {result}")
    return jsonify(result)




@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates"""
    if request.method == 'POST':
        update_data = request.get_json()

        async def process():
            global telegram_app
            if telegram_app is None:
                await setup_telegram()
            update = Update.de_json(update_data, telegram_app.bot)
            await telegram_app.process_update(update)

        asyncio.run(process())
        return 'OK', 200


async def setup_telegram():
    global telegram_app
    from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters
    from groq import Groq
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    async def start(update, context):
        user = update.effective_user
        keyboard = [
            [InlineKeyboardButton("🎬 Video Prompt", callback_data="menu_video"),
             InlineKeyboardButton("🖼️ Image Prompt", callback_data="menu_image")],
            [InlineKeyboardButton("🎨 Choose Style", callback_data="menu_styles"),
             InlineKeyboardButton("❓ Help", callback_data="menu_help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🎬 Welcome to Afrigen Bot, {user.first_name}!\n\n"
            "Africa Creates, AI Generates 🌍\n\n"
            "What would you like to do?",
            reply_markup=reply_markup
        )

    async def handle_message(update, context):
        user_prompt = update.message.text
        style = context.user_data.get('style', 'cinematic')
        mode = context.user_data.get('mode', 'video')

        await update.message.chat.send_action("typing")
        await update.message.reply_text("⏳ Refining your prompt with AI...")

        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system",
                     "content": f"You are an African {mode} prompt engineer. Refine this {style} {mode} prompt into a detailed description. Keep under 200 words. Return ONLY the prompt."},
                    {"role": "user", "content": f"Refine: {user_prompt}"}
                ],
                max_tokens=300
            )
            refined = response.choices[0].message.content

            keyboard = [
                [InlineKeyboardButton("🎬 Video Prompt", callback_data="menu_video"),
                 InlineKeyboardButton("🖼️ Image Prompt", callback_data="menu_image")],
                [InlineKeyboardButton("🎨 Choose Style", callback_data="menu_styles"),
                 InlineKeyboardButton("❓ Help", callback_data="menu_help")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"✨ AI Refined {mode.title()} Prompt:\n\n"
                f"{refined}\n\n"
                f"─────────────────\n"
                f"📋 Copy and use this prompt!\n"
                f"🚀 Full platform: afrigen.onrender.com\n\n"
                f"Africa Creates, AI Generates 🌍",
                reply_markup=reply_markup
            )
        except Exception as e:
            await update.message.reply_text("❌ Sorry, something went wrong! Try again.")
            print(f"Bot error: {e}")

    async def handle_callback(update, context):
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "menu_video":
            context.user_data['mode'] = 'video'
            await query.edit_message_text("🎬 Video Prompt Mode!\n\nType your video idea!")
        elif data == "menu_image":
            context.user_data['mode'] = 'image'
            await query.edit_message_text("🖼️ Image Prompt Mode!\n\nType your image idea!")
        elif data == "menu_help":
            await query.edit_message_text(
                "❓ Help\n\n"
                "/start - Main menu\n"
                "/styles - Choose style\n\n"
                "Just type your idea and get a refined prompt!\n\n"
                "Africa Creates, AI Generates 🌍"
            )
        elif data == "menu_styles":
            keyboard = [
                [InlineKeyboardButton("🎬 Cinematic", callback_data="style_cinematic")],
                [InlineKeyboardButton("🎌 Anime", callback_data="style_anime")],
                [InlineKeyboardButton("🌍 Realistic", callback_data="style_realistic")],
                [InlineKeyboardButton("👑 African", callback_data="style_african")],
                [InlineKeyboardButton("📱 Social Media", callback_data="style_social")],
            ]
            await query.edit_message_text(
                "Choose style:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif data.startswith("style_"):
            style = data.replace("style_", "")
            context.user_data['style'] = style
            await query.edit_message_text(
                f"✅ Style set to: {style.title()}!\n\nNow type your idea!"
            )

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await telegram_app.initialize()
    print("Telegram webhook bot ready!")
@app.route('/robots.txt')
def robots():
    return send_from_directory('static', 'robots.txt')

@app.route('/sitemap.xml')
def sitemap():
    # Built dynamically so blog drafts NEVER leak into the sitemap — only
    # status='published' posts are queried. Static pages are listed first.
    from flask import Response
    from services.blog import get_all_posts

    base = "https://afrigen.com.ng"
    # Only public, crawlable pages — NOT /dashboard (login-gated, redirects
    # crawlers to /login and wastes crawl budget).
    static_pages = [
        ("/", "1.00"),
        ("/blog", "0.80"),
        ("/login", "0.80"),
        ("/register", "0.80"),
        ("/founder", "0.70"),
        ("/upgrade", "0.60"),
        ("/contact", "0.60"),
        ("/docs", "0.60"),
        ("/privacy", "0.40"),
        ("/terms", "0.40"),
    ]

    urls = [f"    <url>\n        <loc>{base}{path}</loc>\n        <priority>{pri}</priority>\n    </url>"
            for path, pri in static_pages]

    for post in get_all_posts():
        urls.append(
            f"    <url>\n        <loc>{base}/blog/{post.slug}</loc>\n"
            f"        <priority>0.70</priority>\n    </url>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return Response(xml, mimetype="application/xml")

@app.route('/ads.txt')
def ads_txt():
    # Served at the domain root (https://afrigen.com.ng/ads.txt) for Google AdSense
    # verification. Force text/plain so AdSense's crawler accepts it.
    return send_from_directory('static', 'ads.txt', mimetype='text/plain')

with app.app_context():
    db.create_all()
    from flask_migrate import upgrade
    upgrade()
    # Seed the original 6 blog posts as published (idempotent — no-op if present).
    try:
        from services.blog import seed_blog_posts
        seeded = seed_blog_posts()
        if seeded:
            print(f"Seeded {seeded} blog posts")
    except Exception as e:
        print(f"Blog seed skipped: {e}")
    print("Afrigen database ready")

if __name__ == '__main__':
    app.run(debug=True)
