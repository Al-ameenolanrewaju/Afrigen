import sys
import os
sys.path.append('/home/Gaminghubcompany/Afrigen')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import re
import asyncio
import logging
import threading

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from config import Config
from models import db, User, TelegramUser, Generation
from services.video import generate_image, generate_video, add_text_overlay
from services.credits import video_gate, image_gate, charge_video, charge_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Minimal Flask app so the bot can use the same SQLAlchemy models (and therefore
# the same credit/limit rules) as the website. We do NOT import app.py here — it
# starts a scheduler, registers blueprints, etc. We only need the DB.
flask_app = Flask(__name__)
flask_app.config.from_object(Config)
# SQLAlchemy 2.x only accepts the "postgresql://" scheme; some hosts still hand
# out "postgres://" (which the old raw psycopg2 path tolerated). Normalize it.
_db_uri = flask_app.config.get("SQLALCHEMY_DATABASE_URI") or ""
if _db_uri.startswith("postgres://"):
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = _db_uri.replace("postgres://", "postgresql://", 1)
db.init_app(flask_app)

# Where the website lives, used in link instructions.
SITE_URL = os.environ.get("SITE_URL", "afrigen.com.ng")

STYLE_PROMPTS = {
    "cinematic": """You are an expert cinematic video prompt engineer.
    Transform the idea into a detailed cinematic prompt with:
    - 4K quality, golden hour lighting
    - Professional camera angles
    - African cultural elements where relevant
    - Mood and atmosphere
    - Technical quality indicators
    Keep under 200 words. Return ONLY the prompt.""",
    "anime": """You are an expert anime video prompt engineer.
    Transform the idea into a detailed anime style prompt with:
    - Japanese anime aesthetic
    - Vibrant colors and dynamic movement
    - Anime art style details
    - African characters with anime styling
    Keep under 200 words. Return ONLY the prompt.""",
    "realistic": """You are an expert realistic video prompt engineer.
    Transform the idea into a hyper-realistic prompt with:
    - Photorealistic details
    - Natural lighting and shadows
    - Real world African settings
    - Ultra high definition quality
    Keep under 200 words. Return ONLY the prompt.""",
    "african": """You are an expert African content video prompt engineer.
    Transform the idea into a rich African aesthetic prompt with:
    - Traditional African clothing and accessories
    - African landscapes and settings
    - Rich cultural elements (Yoruba, Igbo, Hausa etc.)
    - Vibrant African colors and patterns
    Keep under 200 words. Return ONLY the prompt.""",
    "social": """You are an expert social media video prompt engineer.
    Transform the idea into a social media optimized prompt with:
    - Eye-catching visuals
    - Fast paced and dynamic
    - Perfect for TikTok/Instagram/Facebook
    - African content creators style
    Keep under 200 words. Return ONLY the prompt."""
}

IMAGE_STYLE_PROMPTS = {
    "realistic": """You are an expert image prompt engineer.
    Transform the idea into a detailed realistic image prompt with:
    - Photorealistic details
    - Lighting description
    - Camera settings
    - African cultural elements where relevant
    Keep under 150 words. Return ONLY the prompt.""",
    "artistic": """You are an expert artistic image prompt engineer.
    Transform the idea into a detailed artistic prompt with:
    - Art style details
    - Color palette
    - African artistic elements
    Keep under 150 words. Return ONLY the prompt.""",
    "cinematic": """You are an expert cinematic image prompt engineer.
    Transform the idea into a cinematic still image prompt with:
    - Movie still quality
    - Dramatic lighting
    - African cinematic aesthetic
    Keep under 150 words. Return ONLY the prompt.""",
    "african": """You are an expert African art prompt engineer.
    Transform the idea into a rich African aesthetic image prompt with:
    - Traditional African patterns and clothing
    - African landscapes and settings
    - Cultural elements
    Keep under 150 words. Return ONLY the prompt.""",
    "anime": """You are an expert anime image prompt engineer.
    Transform the idea into a detailed anime style prompt with:
    - Japanese anime aesthetic
    - Vibrant colors
    - African characters in anime style
    Keep under 150 words. Return ONLY the prompt.""",
    "social": """You are an expert social media image prompt engineer.
    Transform the idea into a social media optimized image with:
    - Eye-catching composition
    - Vibrant colors
    - Perfect for Instagram/TikTok thumbnails
    Keep under 150 words. Return ONLY the prompt."""
}


def refine_prompt(user_prompt, style="cinematic"):
    from services.provider_manager import provider_manager
    fidelity_rules = (
        "\n\nFIDELITY: Keep the user's core subject, action and intent; enhance "
        "with detail but never replace or drop what they asked for. Preserve any "
        "named people, places, objects or counts. If any words should appear on "
        "screen, copy them VERBATIM in double quotes and make them large, BOLD "
        "and legible. Never paraphrase or invent on-screen words."
    )
    system_message = STYLE_PROMPTS.get(style, STYLE_PROMPTS["cinematic"]) + fidelity_rules
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": (
            "Refine this video prompt. Keep my subject and intent, and keep "
            "any on-screen words exactly as written:\n\n" + user_prompt
        )}
    ]
    with flask_app.app_context():
        return provider_manager.generate_text("Prompt Refinement", messages, max_tokens=300)


def refine_image_prompt(user_prompt, style="realistic"):
    from services.provider_manager import provider_manager
    text_rules = (
        "\n\nCRITICAL: If the idea contains any words to appear in the image "
        "(flyer, billboard, poster, sign, logo), copy them VERBATIM, wrap them "
        "in double quotes, and describe them as large, BOLD, high-contrast and "
        "perfectly legible. Never paraphrase, drop, or invent wording."
    )
    system_message = IMAGE_STYLE_PROMPTS.get(style, IMAGE_STYLE_PROMPTS["realistic"]) + text_rules
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": (
            "Refine this image prompt. Keep any words meant to appear in the "
            "image exactly as written and make them bold and legible:\n\n" + user_prompt
        )}
    ]
    with flask_app.app_context():
        return provider_manager.generate_text("Prompt Refinement", messages, max_tokens=300)


def extract_on_screen_text(text):
    """Pull any double-quoted words from the idea so they can be burned onto the
    video as a caption. Lightweight (regex) so the bot doesn't need the Claude
    API key; returns "" when there's nothing quoted (overlay is then skipped)."""
    if not text:
        return ""
    matches = re.findall(r'"([^"]+)"', text)
    joined = " ".join(m.strip() for m in matches if m.strip())
    return joined[:80]


# ---------- Account linking helpers (all run inside flask_app.app_context()) ----------

def _get_telegram_user(telegram_id):
    return TelegramUser.query.filter_by(telegram_id=str(telegram_id)).first()


def _get_linked_user(telegram_id):
    tgu = _get_telegram_user(telegram_id)
    if tgu and tgu.user_id:
        return db.session.get(User, tgu.user_id)
    return None


def _account_summary(user):
    """Short human-readable line about the user's remaining allowance."""
    if user.plan == 'pro':
        return f"⭐ Pro plan • {user.credits or 0} credits left"
    if user.plan == 'free':
        videos_left = max(0, 3 - (user.monthly_videos_used or 0))
        images_left = max(0, 2 - (user.monthly_images_used or 0))
        return f"🆓 Free plan • {videos_left} videos & {images_left} images left this month"
    return "Account restricted"


def _is_banned(user):
    return user.plan == 'banned' or bool(getattr(user, 'is_banned', False))


def _link_instructions():
    return (
        "🔗 To generate real videos & photos, link your Afrigen account:\n\n"
        f"1️⃣ Sign up or log in at {SITE_URL}\n"
        "2️⃣ Open your Dashboard → *Connect Telegram*\n"
        "3️⃣ Send me the code like this:  /link YOURCODE\n\n"
        "Your free credits and limits are shared with the website."
    )


def _main_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Make Video", callback_data="menu_video"),
         InlineKeyboardButton("🖼️ Make Photo", callback_data="menu_image")],
        [InlineKeyboardButton("🎨 Choose Style", callback_data="menu_styles"),
         InlineKeyboardButton("❓ Help", callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ---------- Commands ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        with flask_app.app_context():
            existing = _get_telegram_user(user.id)
            chat = update.effective_chat
            payload = context.args[0].upper() if context.args else ""
            if payload and chat and chat.type in ("group", "supergroup"):
                account = User.query.filter_by(telegram_link_code=payload).first()
                if account:
                    if not existing:
                        existing = TelegramUser(telegram_id=str(user.id))
                        db.session.add(existing)
                    existing.user_id = account.id
                    existing.chat_id = str(chat.id)
                    existing.chat_title = chat.title or "Telegram group"
                    account.telegram_link_code = None
                    db.session.commit()
                    await update.message.reply_text("Afrigen is connected to this group.")
                    return
            if not existing:
                db.session.add(TelegramUser(
                    telegram_id=str(user.id),
                    username=user.username,
                    first_name=user.first_name,
                ))
                db.session.commit()
            linked = _get_linked_user(user.id) is not None
    except Exception as e:
        logger.error(f"DB error in start: {e}")
        linked = False

    status_line = (
        "✅ Account linked — pick Video or Photo and send your idea!"
        if linked else
        "🔗 Link your Afrigen account with /link to start generating."
    )

    await update.message.reply_text(
        f"🎬 Welcome to Afrigen Bot, {user.first_name}!\n\n"
        "Africa Creates, AI Generates 🌍\n\n"
        f"{status_line}",
        reply_markup=_main_menu()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Afrigen Bot Help*\n\n"
        "Commands:\n"
        "/start - Main menu\n"
        "/link <code> - Connect your Afrigen account\n"
        "/styles - Choose a style\n"
        "/credits - Check your plan & credits\n\n"
        "How to use:\n"
        "1. Link your account with /link (one time)\n"
        "2. Tap *Make Video* or *Make Photo*\n"
        "3. Choose a style (optional)\n"
        "4. Type your idea — I'll generate it! 🎨\n\n"
        "Africa Creates, AI Generates 🌍",
        parse_mode="Markdown"
    )


async def styles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Cinematic", callback_data="style_cinematic")],
        [InlineKeyboardButton("🎌 Anime", callback_data="style_anime")],
        [InlineKeyboardButton("🌍 Realistic", callback_data="style_realistic")],
        [InlineKeyboardButton("👑 African", callback_data="style_african")],
        [InlineKeyboardButton("📱 Social Media", callback_data="style_social")],
    ]
    await update.message.reply_text(
        "🎨 Choose your style:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /link <code>\n\n" + _link_instructions(),
            parse_mode="Markdown"
        )
        return

    code = args[0].strip().upper()
    try:
        with flask_app.app_context():
            account = User.query.filter_by(telegram_link_code=code).first()
            if not account:
                await update.message.reply_text(
                    "❌ That code is invalid or already used.\n\n"
                    f"Grab a fresh one from your Dashboard → Connect Telegram at {SITE_URL}."
                )
                return

            tgu = _get_telegram_user(user.id)
            if not tgu:
                tgu = TelegramUser(
                    telegram_id=str(user.id),
                    username=user.username,
                    first_name=user.first_name,
                )
                db.session.add(tgu)
            tgu.user_id = account.id
            account.telegram_link_code = None  # single-use code
            db.session.commit()

            summary = _account_summary(account)
            account_name = account.username

        await update.message.reply_text(
            f"✅ Linked to your Afrigen account ({account_name})!\n\n"
            f"{summary}\n\n"
            "Now tap *Make Video* or *Make Photo* and send your idea! 🎨",
            reply_markup=_main_menu(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Link error: {e}")
        await update.message.reply_text("❌ Something went wrong linking your account. Please try again.")


async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        with flask_app.app_context():
            account = _get_linked_user(user.id)
            summary = _account_summary(account) if account else None
    except Exception as e:
        logger.error(f"Credits error: {e}")
        await update.message.reply_text("❌ Error fetching your stats!")
        return

    if not summary:
        await update.message.reply_text(
            "📊 You haven't linked an account yet.\n\n" + _link_instructions(),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"📊 *Your Afrigen Account*\n\n{summary}\n\n"
        f"Top up or upgrade at {SITE_URL}/upgrade\n\n"
        "Africa Creates, AI Generates 🇳🇬",
        parse_mode="Markdown"
    )


# ---------- Menu / style callbacks ----------

async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_video":
        context.user_data['mode'] = 'video'
        await query.edit_message_text(
            "🎬 Video mode on!\n\n"
            "Send your idea and I'll generate a video.\n\n"
            "Example: 'A Nigerian king walking through Lagos at sunset'"
        )
        return

    elif data == "menu_image":
        context.user_data['mode'] = 'image'
        await query.edit_message_text(
            "🖼️ Photo mode on!\n\n"
            "Send your idea and I'll generate a photo.\n\n"
            "Example: 'A Yoruba queen in traditional attire'"
        )
        return

    elif data == "menu_help":
        await query.edit_message_text(
            "❓ Afrigen Bot Help\n\n"
            "Commands:\n"
            "/start - Main menu\n"
            "/link <code> - Connect your account\n"
            "/styles - Choose style\n"
            "/credits - Check plan & credits\n\n"
            "Tap Make Video or Make Photo, then send your idea!\n\n"
            "Africa Creates, AI Generates 🌍"
        )
        return

    elif data == "menu_styles":
        keyboard = [
            [InlineKeyboardButton("🎬 Cinematic", callback_data="style_cinematic")],
            [InlineKeyboardButton("🎌 Anime", callback_data="style_anime")],
            [InlineKeyboardButton("🌍 Realistic", callback_data="style_realistic")],
            [InlineKeyboardButton("👑 African", callback_data="style_african")],
            [InlineKeyboardButton("📱 Social Media", callback_data="style_social")],
        ]
        await query.edit_message_text(
            "🎨 Choose your style:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    style = data.replace("style_", "")
    context.user_data['style'] = style

    style_names = {
        "cinematic": "🎬 Cinematic",
        "anime": "🎌 Anime",
        "realistic": "🌍 Realistic",
        "african": "👑 African",
        "social": "📱 Social Media"
    }

    await query.edit_message_text(
        f"✅ Style set to: {style_names.get(style, style)}\n\n"
        "Now send your idea and I'll generate it!"
    )


# ---------- Core generation ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    user_prompt = update.message.text
    style = context.user_data.get('style', 'cinematic')
    mode = context.user_data.get('mode', 'video')

    # 1) Require a linked account, then gate against the shared plan/credit rules.
    extended = False
    try:
        with flask_app.app_context():
            account = _get_linked_user(tg.id)
            if account is None:
                await update.message.reply_text(_link_instructions(), parse_mode="Markdown")
                return
            if _is_banned(account):
                await update.message.reply_text("❌ Your account is restricted.")
                return

            if mode == 'image':
                ok, error = image_gate(account)
                cost = 0
            else:
                # Pro users get the premium 10s Kling clip (same as the website);
                # everyone else gets the short clip. The gate prices accordingly.
                extended = (account.plan == 'pro')
                ok, error, cost = video_gate(account, style, extended=extended)

            if not ok:
                await update.message.reply_text(f"❌ {error}")
                return

            account_id = account.id
    except Exception as e:
        logger.error(f"Gate error: {e}")
        await update.message.reply_text("❌ Something went wrong. Please try again.")
        return

    # 2) Refine the idea.
    await update.message.chat.send_action("typing")
    await update.message.reply_text("⏳ Refining your idea with AI...")
    try:
        if mode == 'image':
            refined = refine_image_prompt(user_prompt, style)
        else:
            refined = refine_prompt(user_prompt, style)
    except Exception as e:
        logger.error(f"Refine error: {e}")
        await update.message.reply_text("❌ Couldn't refine your idea right now. Please try again.")
        return

    # 3) Generate the media (blocking fal call off the event loop).
    if mode == 'image':
        await update.message.chat.send_action("upload_photo")
        await update.message.reply_text("🎨 Generating your photo... give me a moment.")
        result = await asyncio.to_thread(generate_image, refined, style, "1:1")
        success = bool(result.get("success"))
        media_url = result.get("image_url")
        gen_error = result.get("error")
    else:
        await update.message.chat.send_action("upload_video")
        wait_note = "this can take 2-5 minutes" if extended else "this can take 1-3 minutes"
        await update.message.reply_text(f"🎬 Generating your video... {wait_note}.")
        result = await asyncio.to_thread(generate_video, refined, style, "16:9", extended)
        success = bool(result.get("success"))
        media_url = result.get("video_url")
        gen_error = result.get("error")

    # 4) Failure: record it, charge nothing.
    if not success or not media_url:
        try:
            with flask_app.app_context():
                db.session.add(Generation(
                    user_id=account_id,
                    original_prompt=user_prompt,
                    refined_prompt=refined,
                    generation_type="image" if mode == 'image' else "text",
                    status="failed",
                    credit_cost=cost or 5,
                ))
                db.session.commit()
        except Exception as e:
            logger.error(f"Failed-generation log error: {e}")
        await update.message.reply_text(f"❌ {gen_error or 'Generation failed. Please try again.'}")
        return

    # 5) Burn any quoted on-screen words onto videos (best-effort).
    if mode == 'video':
        on_screen = extract_on_screen_text(user_prompt)
        if on_screen:
            try:
                media_url = await asyncio.to_thread(add_text_overlay, media_url, on_screen)
            except Exception as e:
                logger.error(f"Overlay error: {e}")

    # 6) Charge on success + record the generation, then read remaining allowance.
    summary = ""
    try:
        with flask_app.app_context():
            account = db.session.get(User, account_id)
            if mode == 'image':
                charge_image(account)
                gen = Generation(
                    user_id=account_id,
                    original_prompt=user_prompt,
                    refined_prompt=refined,
                    image_url=media_url,
                    generation_type="image",
                    status="completed",
                )
            else:
                charge_video(account, cost)
                gen = Generation(
                    user_id=account_id,
                    original_prompt=user_prompt,
                    refined_prompt=refined,
                    video_url=media_url,
                    generation_type="text",
                    status="completed",
                    credit_cost=cost,
                )
            db.session.add(gen)

            tgu = _get_telegram_user(tg.id)
            if tgu:
                tgu.prompts_refined = (tgu.prompts_refined or 0) + 1
            db.session.commit()
            summary = _account_summary(account)
    except Exception as e:
        logger.error(f"Charge/record error: {e}")

    # 7) Deliver the media.
    caption = (
        "✨ Made with Afrigen\n"
        f"{summary}\n\n"
        "Africa Creates, AI Generates 🌍"
    )
    try:
        if mode == 'image':
            await update.message.reply_photo(media_url, caption=caption, reply_markup=_main_menu())
        else:
            await update.message.reply_video(media_url, caption=caption, reply_markup=_main_menu())
    except Exception as e:
        # If Telegram can't fetch/host the media, at least hand over the link.
        logger.error(f"Send media error: {e}")
        await update.message.reply_text(
            f"✅ Done! Here's your {'photo' if mode == 'image' else 'video'}:\n{media_url}",
            reply_markup=_main_menu()
        )


def run_bot():
    try:
        print("🚀 Starting bot...")
        print("TOKEN:", bool(TOKEN))

        # Lightweight health-check server so the host (Railway/Render) sees a
        # live port.
        from flask import Flask as HealthFlask
        health_app = HealthFlask("afrigen_health")

        @health_app.route('/')
        def health():
            return "Afrigen Bot is running! 🤖", 200

        PORT = int(os.environ.get("PORT", 10000))
        threading.Thread(
            target=lambda: health_app.run(host='0.0.0.0', port=PORT),
            daemon=True
        ).start()

        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("link", link_command))
        app.add_handler(CommandHandler("styles", styles_command))
        app.add_handler(CommandHandler("credits", credits_command))
        app.add_handler(CallbackQueryHandler(handle_style_selection))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        print("🤖 Bot running with polling...")
        app.run_polling()

    except Exception:
        import traceback
        print("❌ STARTUP ERROR:")
        traceback.print_exc()
        import time
        time.sleep(30)  # keep the process alive so the host shows the error


if __name__ == "__main__":
    run_bot()
