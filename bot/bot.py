import sys
import os
from dotenv import load_dotenv
load_dotenv()

import re
import asyncio
import logging
import threading

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from config import Config
from models import db, User, TelegramUser, Generation
from services.video import generate_image, generate_video, add_text_overlay
from services.credits import video_gate, image_gate, charge_video, charge_image

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

flask_app = Flask(__name__)
flask_app.config.from_object(Config)
_db_uri = flask_app.config.get("SQLALCHEMY_DATABASE_URI") or ""
if _db_uri.startswith("postgres://"):
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = _db_uri.replace("postgres://", "postgresql://", 1)
db.init_app(flask_app)

SITE_URL = os.environ.get("SITE_URL", "afrigen.com.ng")

STYLE_PROMPTS = {
    "cinematic": "You are an expert cinematic video prompt engineer.\nTransform the idea into a detailed cinematic prompt with:\n- 4K quality, golden hour lighting\n- Professional camera angles\n- African cultural elements where relevant\n- Mood and atmosphere\n- Technical quality indicators\nKeep under 200 words. Return ONLY the prompt.",
    "anime": "You are an expert anime video prompt engineer.\nTransform the idea into a detailed anime style prompt with:\n- Japanese anime aesthetic\n- Vibrant colors and dynamic movement\n- Anime art style details\n- African characters with anime styling\nKeep under 200 words. Return ONLY the prompt.",
    "realistic": "You are an expert realistic video prompt engineer.\nTransform the idea into a hyper-realistic prompt with:\n- Photorealistic details\n- Natural lighting and shadows\n- Real world African settings\n- Ultra high definition quality\nKeep under 200 words. Return ONLY the prompt.",
    "african": "You are an expert African content video prompt engineer.\nTransform the idea into a rich African aesthetic prompt with:\n- Traditional African clothing and accessories\n- African landscapes and settings\n- Rich cultural elements (Yoruba, Igbo, Hausa etc.)\n- Vibrant African colors and patterns\nKeep under 200 words. Return ONLY the prompt.",
    "social": "You are an expert social media video prompt engineer.\nTransform the idea into a social media optimized prompt with:\n- Eye-catching visuals\n- Fast paced and dynamic\n- Perfect for TikTok/Instagram/Facebook\n- African content creators style\nKeep under 200 words. Return ONLY the prompt."
}

IMAGE_STYLE_PROMPTS = {
    "realistic": "You are an expert image prompt engineer.\nTransform the idea into a detailed realistic image prompt with:\n- Photorealistic details\n- Lighting description\n- Camera settings\n- African cultural elements where relevant\nKeep under 150 words. Return ONLY the prompt.",
    "artistic": "You are an expert artistic image prompt engineer.\nTransform the idea into a detailed artistic prompt with:\n- Art style details\n- Color palette\n- African artistic elements\nKeep under 150 words. Return ONLY the prompt.",
    "cinematic": "You are an expert cinematic image prompt engineer.\nTransform the idea into a cinematic still image prompt with:\n- Movie still quality\n- Dramatic lighting\n- African cinematic aesthetic\nKeep under 150 words. Return ONLY the prompt.",
    "african": "You are an expert African art prompt engineer.\nTransform the idea into a rich African aesthetic image prompt with:\n- Traditional African patterns and clothing\n- African landscapes and settings\n- Cultural elements\nKeep under 150 words. Return ONLY the prompt.",
    "anime": "You are an expert anime image prompt engineer.\nTransform the idea into a detailed anime style prompt with:\n- Japanese anime aesthetic\n- Vibrant colors\n- African characters in anime style\nKeep under 150 words. Return ONLY the prompt.",
    "social": "You are an expert social media image prompt engineer.\nTransform the idea into a social media optimized image with:\n- Eye-catching composition\n- Vibrant colors\n- Perfect for Instagram/TikTok thumbnails\nKeep under 150 words. Return ONLY the prompt."
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
        return provider_manager.generate_text("Prompt Refinement", messages, max_tokens=2048)

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
        return provider_manager.generate_text("Prompt Refinement", messages, max_tokens=2048)

def extract_on_screen_text(text):
    if not text:
        return ""
    matches = re.findall(r'"([^"]+)"', text)
    joined = " ".join(m.strip() for m in matches if m.strip())
    return joined[:80]

def _get_telegram_user(telegram_id):
    return TelegramUser.query.filter_by(telegram_id=str(telegram_id)).first()

def _get_linked_user(telegram_id):
    tgu = _get_telegram_user(telegram_id)
    if tgu and tgu.user_id:
        return db.session.get(User, tgu.user_id)
    return None

def _account_summary(user):
    if user.plan == 'pro':
        return f"⭐ Pro plan • {user.credits or 0} credits left"
    if user.plan == 'free':
        videos_left = max(0, 3 - (user.monthly_videos_used or 0))
        images_left = max(0, 2 - (user.monthly_images_used or 0))
        return f"🆓 Free plan • Video generation requires Pro • {images_left} images left"
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

# ----- ASYNC DB HELPERS -----

async def _async_start_db(tg_id, username, first_name, payload, chat_id, chat_title, chat_type):
    def _do():
        with flask_app.app_context():
            existing = _get_telegram_user(tg_id)
            if payload and chat_type in ("group", "supergroup"):
                account = User.query.filter_by(telegram_link_code=payload).first()
                if account:
                    if not existing:
                        existing = TelegramUser(telegram_id=str(tg_id))
                        db.session.add(existing)
                    existing.user_id = account.id
                    existing.chat_id = str(chat_id)
                    existing.chat_title = chat_title or "Telegram group"
                    account.telegram_link_code = None
                    db.session.commit()
                    return True, "Afrigen is connected to this group."
            if not existing:
                db.session.add(TelegramUser(telegram_id=str(tg_id), username=username, first_name=first_name))
                db.session.commit()
            linked = _get_linked_user(tg_id) is not None
            return False, linked
    return await asyncio.to_thread(_do)

async def _async_link_account(tg_id, username, first_name, code):
    def _do():
        with flask_app.app_context():
            account = User.query.filter_by(telegram_link_code=code).first()
            if not account:
                return False, None, None
            tgu = _get_telegram_user(tg_id)
            if not tgu:
                tgu = TelegramUser(telegram_id=str(tg_id), username=username, first_name=first_name)
                db.session.add(tgu)
            tgu.user_id = account.id
            account.telegram_link_code = None
            db.session.commit()
            return True, _account_summary(account), account.username
    return await asyncio.to_thread(_do)

async def _async_get_credits(tg_id):
    def _do():
        with flask_app.app_context():
            account = _get_linked_user(tg_id)
            return _account_summary(account) if account else None
    return await asyncio.to_thread(_do)

async def _async_get_gate_status(tg_id, mode, style):
    def _do():
        with flask_app.app_context():
            account = _get_linked_user(tg_id)
            if not account:
                return False, _link_instructions(), 0, None, False, "free"
            if _is_banned(account):
                return False, "❌ Your account is restricted.", 0, None, False, account.plan
            extended = (account.plan == 'pro')
            if mode == 'image':
                ok, err = image_gate(account)
                cost = 0
            else:
                ok, err, cost = video_gate(account, style, extended=extended)
            return ok, err, cost, account.id, extended, account.plan
    return await asyncio.to_thread(_do)

async def _async_record_failed(mode, account_id, user_prompt, refined, cost):
    def _do():
        with flask_app.app_context():
            db.session.add(Generation(
                user_id=account_id, original_prompt=user_prompt, refined_prompt=refined,
                generation_type="image" if mode == 'image' else "text",
                status="failed", credit_cost=cost or 5
            ))
            db.session.commit()
    await asyncio.to_thread(_do)

async def _async_charge_and_record(mode, account_id, tg_id, user_prompt, refined, media_url, cost):
    def _do():
        with flask_app.app_context():
            account = db.session.get(User, account_id)
            if mode == 'image':
                charge_image(account)
                gen = Generation(
                    user_id=account_id, original_prompt=user_prompt, refined_prompt=refined,
                    image_url=media_url, generation_type="image", status="completed"
                )
            else:
                charge_video(account, cost)
                gen = Generation(
                    user_id=account_id, original_prompt=user_prompt, refined_prompt=refined,
                    video_url=media_url, generation_type="text", status="completed", credit_cost=cost
                )
            db.session.add(gen)
            tgu = _get_telegram_user(tg_id)
            if tgu:
                tgu.prompts_refined = (tgu.prompts_refined or 0) + 1
            db.session.commit()
            return _account_summary(account)
    return await asyncio.to_thread(_do)

# ---------- Commands ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    payload = context.args[0].upper() if context.args else ""
    
    try:
        is_group_msg, result = await _async_start_db(user.id, user.username, user.first_name, payload, chat.id if chat else None, chat.title if chat else None, chat.type if chat else None)
        if is_group_msg:
            await update.message.reply_text(result)
            return
        linked = result
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
    await update.message.reply_text("🎨 Choose your style:", reply_markup=InlineKeyboardMarkup(keyboard))

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /link <code>\n\n" + _link_instructions(), parse_mode="Markdown")
        return

    code = args[0].strip().upper()
    try:
        success, summary, account_name = await _async_link_account(user.id, user.username, user.first_name, code)
        if not success:
            await update.message.reply_text(f"❌ That code is invalid or already used.\n\nGrab a fresh one from your Dashboard → Connect Telegram at {SITE_URL}.")
            return
            
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
        summary = await _async_get_credits(user.id)
    except Exception as e:
        logger.error(f"Credits error: {e}")
        await update.message.reply_text("❌ Error fetching your stats!")
        return

    if not summary:
        await update.message.reply_text("📊 You haven't linked an account yet.\n\n" + _link_instructions(), parse_mode="Markdown")
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
    logger.info(f"Callback query received: {query.data} from {update.effective_user.id}")
    await query.answer()
    data = query.data

    try:
        if data == "menu_video":
            context.user_data['mode'] = 'video'
            await query.edit_message_text("🎬 Video mode on!\n\nSend your idea and I'll generate a video.\n\nExample: 'A Nigerian king walking through Lagos at sunset'")
            return
        elif data == "menu_image":
            context.user_data['mode'] = 'image'
            await query.edit_message_text("🖼️ Photo mode on!\n\nSend your idea and I'll generate a photo.\n\nExample: 'A Yoruba queen in traditional attire'")
            return
        elif data == "menu_help":
            await query.edit_message_text(
                "❓ Afrigen Bot Help\n\n"
                "Commands:\n/start - Main menu\n/link <code> - Connect your account\n/styles - Choose style\n/credits - Check plan & credits\n\n"
                "Tap Make Video or Make Photo, then send your idea!\n\nAfrica Creates, AI Generates 🌍"
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
            await query.edit_message_text("🎨 Choose your style:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        style = data.replace("style_", "")
        context.user_data['style'] = style
        style_names = {"cinematic": "🎬 Cinematic", "anime": "🎌 Anime", "realistic": "🌍 Realistic", "african": "👑 African", "social": "📱 Social Media"}
        await query.edit_message_text(f"✅ Style set to: {style_names.get(style, style)}\n\nNow send your idea and I'll generate it!")
    except Exception as e:
        from telegram.error import BadRequest
        if isinstance(e, BadRequest) and "Message is not modified" in str(e):
            pass
        else:
            logger.exception(f"Error editing message in callback: {e}")

# ---------- Core generation ----------

async def _generation_task(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_prompt: str, style: str, mode: str, account_id: int, tg_id: int, extended: bool, cost: int, plan: str):
    # 2) Refine the idea.
    try:
        if mode == 'image':
            refined = await asyncio.to_thread(refine_image_prompt, user_prompt, style)
        else:
            refined = await asyncio.to_thread(refine_prompt, user_prompt, style)
    except Exception as e:
        logger.error(f"Refine error: {e}")
        await context.bot.send_message(chat_id, "❌ Couldn't refine your idea right now. Please try again.")
        return

    # 3) Generate the media
    try:
        if mode == 'image':
            await context.bot.send_message(chat_id, "🎨 Generating your photo... give me a moment.")
            provider = "fal" if plan == "pro" else "huggingface"
            result = await asyncio.to_thread(generate_image, refined, style, "1:1", provider)
        else:
            wait_note = "this can take 2-5 minutes" if extended else "this can take 1-3 minutes"
            await context.bot.send_message(chat_id, f"🎬 Generating your video... {wait_note}.")
            result = await asyncio.to_thread(generate_video, refined, style, "16:9", extended, plan == 'pro')
    except Exception as e:
        logger.error(f"Generate error: {e}")
        result = {"success": False, "error": str(e)}

    success = bool(result.get("success"))
    media_url = result.get("image_url") if mode == 'image' else result.get("video_url")
    gen_error = result.get("error")

    # 4) Failure
    if not success or not media_url:
        try:
            await _async_record_failed(mode, account_id, user_prompt, refined, cost)
        except Exception as e:
            logger.error(f"Failed-generation log error: {e}")
        logger.error(f"Generation failed for account {account_id}: {gen_error}")
        await context.bot.send_message(chat_id, f"❌ Generation failed: {gen_error}\nPlease try again later.")
        return

    # 5) Overlay
    if mode == 'video':
        on_screen = extract_on_screen_text(user_prompt)
        if on_screen:
            try:
                media_url = await asyncio.to_thread(add_text_overlay, media_url, on_screen)
            except Exception as e:
                logger.error(f"Overlay error: {e}")

    # 6) Charge on success
    try:
        summary = await _async_charge_and_record(mode, account_id, tg_id, user_prompt, refined, media_url, cost)
    except Exception as e:
        logger.error(f"Charge/record error: {e}")
        summary = ""

    # 7) Deliver
    caption = f"✨ Made with Afrigen\n{summary}\n\nAfrica Creates, AI Generates 🌍"
    try:
        if mode == 'image':
            await context.bot.send_photo(chat_id, media_url, caption=caption, reply_markup=_main_menu())
        else:
            await context.bot.send_video(chat_id, media_url, caption=caption, reply_markup=_main_menu())
    except Exception as e:
        logger.error(f"Send media error: {e}")
        await context.bot.send_message(chat_id, f"✅ Done! Here's your {'photo' if mode == 'image' else 'video'}:\n{media_url}", reply_markup=_main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    chat_id = update.effective_chat.id
    user_prompt = update.message.text
    style = context.user_data.get('style', 'cinematic')
    mode = context.user_data.get('mode', 'video')

    # 1) Check account and gates
    try:
        ok, error, cost, account_id, extended, plan = await _async_get_gate_status(tg.id, mode, style)
        if not ok:
            await update.message.reply_text(error, parse_mode="Markdown" if "🔗" in error else None)
            return
    except Exception as e:
        logger.error(f"Gate error: {e}")
        await update.message.reply_text("❌ Something went wrong. Please try again.")
        return

    await update.message.chat.send_action("typing")
    # Spin up background task
    context.application.create_task(
        _generation_task(context, chat_id, user_prompt, style, mode, account_id, tg.id, extended, cost, plan)
    )

async def post_init(application: Application):
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Cleared any leftover webhooks")
    except Exception as e:
        logger.exception("Failed to delete webhook")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    from telegram.error import Conflict
    if isinstance(context.error, Conflict):
        logger.warning("Telegram Conflict error ignored (expected during zero-downtime deployments).")
    else:
        logger.exception("Exception while handling an update:", exc_info=context.error)
        if isinstance(update, Update) and update.callback_query:
            try:
                await update.callback_query.answer("Something went wrong, try /start again", show_alert=True)
            except Exception:
                pass

def run_bot():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is missing or empty. Cannot start bot.")
        sys.exit(1)

    try:
        print("🚀 Starting bot...")
        
        from flask import Flask as HealthFlask
        health_app = HealthFlask("afrigen_health")
        @health_app.route('/')
        def health():
            return "Afrigen Bot is running! 🤖", 200

        PORT = int(os.environ.get("PORT", 10000))
        threading.Thread(
            target=lambda: health_app.run(host='0.0.0.0', port=PORT, use_reloader=False),
            daemon=True
        ).start()

        app = Application.builder().token(TOKEN).concurrent_updates(True).post_init(post_init).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("link", link_command))
        app.add_handler(CommandHandler("styles", styles_command))
        app.add_handler(CommandHandler("credits", credits_command))
        app.add_handler(CallbackQueryHandler(handle_style_selection))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)

        print("🤖 Bot running with polling...")
        app.run_polling()

    except Exception:
        import traceback
        print("❌ STARTUP ERROR:")
        traceback.print_exc()
        import time
        time.sleep(30)

if __name__ == "__main__":
    run_bot()
