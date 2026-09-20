import os
import sys
import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, redirect, url_for, request, session, jsonify, Response, send_from_directory
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail, Message
from flask_apscheduler import APScheduler
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

from models import db, User, Generation, TelegramUser, SavedPrompt, Referral
from config import DevelopmentConfig, ProductionConfig, TestingConfig
from extensions import csrf, limiter
from routes.main import main
from routes.auth import auth
from routes.api import api
from routes.campaigns import campaigns_bp
from services.credits import refund_video
from constants import (
    FACEBOOK_URL, TWITTER_URL, INSTAGRAM_URL, LINKEDIN_URL, TELEGRAM_URL
)

app = Flask(__name__)
app.url_map.strict_slashes = False


def get_missing_required_env_vars():
    """Return the set of required env vars for the current deployment."""
    required = {
        "SECRET_KEY": "Flask session signing and auth token security",
        "DATABASE_URL": "Database connection for the app",
        "GROQ_API_KEY": "AI assistant and content generation flows",
        "FAL_KEY": "Video/image generation provider",
        "PAYSTACK_SECRET_KEY": "Payments and Pro upgrades",
        "PAYSTACK_PUBLIC_KEY": "Frontend payment initialization",
        "HF_TOKEN": "Hugging Face API token for free image generation",
    }
    return [key for key, _ in required.items() if not os.environ.get(key)]


app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
is_production = (
    os.environ.get("RENDER", "").lower() == "true"
    or os.environ.get("FLASK_ENV") == "production"
)
pytest_mode = (
    "pytest" in sys.modules
    or any("pytest" in arg.lower() for arg in sys.argv)
    or os.environ.get("PYTEST_CURRENT_TEST") is not None
)
app.config.from_object(TestingConfig if pytest_mode else (ProductionConfig if is_production else DevelopmentConfig))
if is_production and not app.config.get("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY must be configured in production.")
limiter.init_app(app)
csrf.init_app(app)


@app.before_request
def capture_signup_tracking():
    utm_source = request.args.get('utm_source')
    ref_code = request.args.get('ref')
    if utm_source and 'signup_source' not in session:
        session['signup_source'] = utm_source
    if ref_code and 'ref_code' not in session:
        session['ref_code'] = ref_code


mail = Mail(app)
oauth = OAuth(app)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
telegram_app = None

db.init_app(app)
from services.newsletter import sync_all_users_to_subscribers
from services.webhook_tasks import start_webhook_worker
migrate = Migrate(app, db)

with app.app_context():
    try:
        if db.inspect(db.engine).has_table('users'):
            sync_all_users_to_subscribers()
    except Exception:
        pass

start_webhook_worker(app)
login_manager = LoginManager(app)
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    if user:
        from routes.main import is_admin_user
        if is_admin_user(user):
            # Ensure in-memory admin properties are set without forcing constant DB writes
            if user.plan != 'pro' or (user.credits or 0) < 900000:
                user.plan = 'pro'
                user.credits = 999999
    return user


google = oauth.register(
    name='google',
    client_id=app.config.get('GOOGLE_CLIENT_ID'),
    client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


@scheduler.task('interval', id='fail_stuck_generations', minutes=5)
def fail_stuck_generations():
    """Rescue videos orphaned in 'processing'."""
    from datetime import datetime, timedelta, timezone
    with app.app_context():
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
            # Query without row lock: we don't need with_for_update() here since:
            # 1. The status change to 'failed' is idempotent
            # 2. Multiple concurrent runs won't cause data corruption (both set status='failed')
            # 3. Using with_for_update() fails on read-only database replicas
            stuck = Generation.query.filter(
                Generation.status == 'processing',
                Generation.created_at < cutoff,
            ).all()
            if not stuck:
                return
            for gen in stuck:
                gen.status = 'failed'
                user = db.session.get(User, gen.user_id)
                if user:
                    refund_video(user, gen.credit_cost)
                gen.refund_applied = True
            db.session.commit()
            print(f"⏱️ Failed {len(stuck)} stuck generation(s) past the 15-min timeout.")
        except Exception as e:
            db.session.rollback()
            print(f"Error in fail_stuck_generations: {e}")


@scheduler.task('cron', id='alert_failed_generation_rate', hour=23, minute=55)
def alert_failed_generation_rate():
    from datetime import datetime, timedelta, timezone
    with app.app_context():
        since = datetime.now(timezone.utc) - timedelta(days=1)
        total = Generation.query.filter(Generation.created_at >= since).count()
        failed = Generation.query.filter(Generation.created_at >= since, Generation.status == 'failed').count()
        if total >= 10 and failed / total >= 0.5:
            try:
                from services.alerts import notify_admin_alert
                notify_admin_alert("Generation failure rate spike", f"{failed} of {total} generations failed in the last 24 hours.")
            except Exception as exc:
                print(f"Failure-rate alert error: {exc}")


@scheduler.task('interval', id='process_publishing_queue', seconds=30)
def process_publishing_queue():
    """Poll the publishing retry queue every 30 seconds."""
    with app.app_context():
        try:
            from services.connected_accounts.queue import process_queue
            process_queue()
        except Exception as e:
            print(f"Publishing queue processor error: {e}")


@scheduler.task('cron', id='generate_weekly_newsletter', day_of_week='sat', hour=9)
def generate_weekly_newsletter():
    with app.app_context():
        try:
            from services.newsletter import run_weekly_generation
            run_weekly_generation()
        except Exception as e:
            print(f"Weekly newsletter generation failed: {e}")


@scheduler.task('cron', id='send_weekly_newsletter', day_of_week='mon', hour=9)
def send_weekly_newsletter():
    with app.app_context():
        try:
            from services.newsletter import run_weekly_send
            run_weekly_send()
        except Exception as e:
            print(f"Weekly newsletter send failed: {e}")


@scheduler.task('cron', id='generate_daily_blog_draft', hour=7)
def generate_daily_blog_draft():
    with app.app_context():
        try:
            from services.blog import run_daily_draft_generation
            run_daily_draft_generation()
        except Exception as e:
            print(f"Daily blog draft generation failed: {e}")


@scheduler.task('cron', id='generate_daily_content', hour=10)
def generate_daily_content():
    with app.app_context():
        try:
            from content_engine.pipeline import ContentPipeline
            pipeline = ContentPipeline()
            pipeline.run_automatic()
        except Exception as e:
            print(f"Daily Content Engine generation failed: {e}")


# Setup logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

file_handler = RotatingFileHandler(
    'logs/afrigen.log',
    maxBytes=10240000,
    backupCount=10
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s %(message)s'
))
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)

missing = get_missing_required_env_vars()
if missing:
    logger.warning("Missing required environment variables: %s", ", ".join(missing))
else:
    logger.info("All required environment variables are present.")
logger.info('Afrigen startup!')

app.register_blueprint(main)
app.register_blueprint(auth, url_prefix='/auth')
app.register_blueprint(api, url_prefix='/api/v1')
app.register_blueprint(campaigns_bp, url_prefix='/api/campaigns')


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


@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='favicon.png'))


@app.route(f'/webhook/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates using safe event loop handling."""
    if request.method == 'POST':
        update_data = request.get_json()

        async def process():
            global telegram_app
            if telegram_app is None:
                await setup_telegram()
            from telegram import Update
            update = Update.de_json(update_data, telegram_app.bot)
            await telegram_app.process_update(update)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            asyncio.ensure_future(process(), loop=loop)
        else:
            loop.run_until_complete(process())

        return 'OK', 200


async def setup_telegram():
    global telegram_app
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from services.provider_manager import provider_manager

    async def start(update, context):
        user = update.effective_user
        chat = update.effective_chat
        payload = context.args[0].upper() if context.args else ""
        if payload and chat and chat.type in ("group", "supergroup"):
            with app.app_context():
                account = User.query.filter_by(telegram_link_code=payload).first()
                if account:
                    telegram_user = TelegramUser.query.filter_by(telegram_id=str(user.id)).first()
                    if not telegram_user:
                        telegram_user = TelegramUser(telegram_id=str(user.id))
                        db.session.add(telegram_user)
                    telegram_user.user_id = account.id
                    telegram_user.chat_id = str(chat.id)
                    telegram_user.chat_title = chat.title or "Telegram group"
                    account.telegram_link_code = None
                    db.session.commit()
                    await update.message.reply_text("Afrigen is connected to this group.")
                    return
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

    async def link_command(update, context):
        user = update.effective_user
        if not context.args:
            await update.message.reply_text("Usage: /link <code>")
            return

        code = context.args[0].strip().upper()
        with app.app_context():
            account = User.query.filter_by(telegram_link_code=code).first()
            if not account:
                await update.message.reply_text(
                    "That code is invalid or already used. Generate a fresh code from your Afrigen Dashboard."
                )
                return

            telegram_user = TelegramUser.query.filter_by(telegram_id=str(user.id)).first()
            if not telegram_user:
                telegram_user = TelegramUser(
                    telegram_id=str(user.id),
                    username=user.username,
                    first_name=user.first_name,
                )
                db.session.add(telegram_user)
            telegram_user.user_id = account.id
            account.telegram_link_code = None
            db.session.commit()

        await update.message.reply_text(
            "Your Afrigen account is connected. You can now generate from the Afrigen bot."
        )

    async def handle_message(update, context):
        user_prompt = update.message.text
        style = context.user_data.get('style', 'cinematic')
        mode = context.user_data.get('mode', 'video')

        await update.message.chat.send_action("typing")
        await update.message.reply_text("⏳ Refining your prompt with AI...")

        try:
            messages = [
                {
                    "role": "system",
                    "content": f"You are an African {mode} prompt engineer. Refine this {style} {mode} prompt into a detailed description. Keep under 200 words. Return ONLY the prompt."
                },
                {"role": "user", "content": f"Refine: {user_prompt}"}
            ]

            # Integrated with provider_manager for failover support
            refined = provider_manager.generate_text(
                task_type="Prompt Refinement",
                messages=messages,
                max_tokens=2048
            )

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
    telegram_app.add_handler(CommandHandler("link", link_command))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await telegram_app.initialize()
    print("Telegram webhook bot ready!")


@app.route('/robots.txt')
def robots():
    return send_from_directory('static', 'robots.txt')


@app.route('/sitemap.xml')
def sitemap():
    from services.blog import get_all_posts

    base = "https://afrigen.com.ng"
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
    return send_from_directory('static', 'ads.txt', mimetype='text/plain')


if __name__ == '__main__':
    app.run(debug=True)