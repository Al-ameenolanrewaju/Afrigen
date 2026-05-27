import sys
import os
sys.path.append('/home/Gaminghubcompany/Afrigen')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from groq import Groq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

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
    system_message = STYLE_PROMPTS.get(style, STYLE_PROMPTS["cinematic"])
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Refine this video prompt: {user_prompt}"}
        ],
        max_tokens=300
    )
    return response.choices[0].message.content

def refine_image_prompt(user_prompt, style="realistic"):
    system_message = IMAGE_STYLE_PROMPTS.get(style, IMAGE_STYLE_PROMPTS["realistic"])
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Refine this image prompt: {user_prompt}"}
        ],
        max_tokens=200
    )
    return response.choices[0].message.content

def get_db_connection():
    import psycopg2
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    print(f"Start called by: {user.first_name}")

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM telegram_users WHERE telegram_id = %s",
            (str(user.id),)
        )
        existing = cursor.fetchone()
        if not existing:
            cursor.execute(
                "INSERT INTO telegram_users (telegram_id, username, first_name) VALUES (%s, %s, %s)",
                (str(user.id), user.username, user.first_name)
            )
            connection.commit()
            print(f"New Telegram user saved: {user.first_name}")
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"DB error: {e}")

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 Afrigen Bot Help\n\n"
        "Commands:\n"
        "/start - Main menu\n"
        "/styles - Choose video style\n"
        "/credits - Check your stats\n"
        "/history - See past prompts\n\n"
        "How to use:\n"
        "1. Choose Video or Image mode\n"
        "2. Choose your style\n"
        "3. Type your idea\n"
        "4. Get refined prompt!\n\n"
        "Africa Creates, AI Generates 🌍"
    )

async def styles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Cinematic", callback_data="style_cinematic")],
        [InlineKeyboardButton("🎌 Anime", callback_data="style_anime")],
        [InlineKeyboardButton("🌍 Realistic", callback_data="style_realistic")],
        [InlineKeyboardButton("👑 African", callback_data="style_african")],
        [InlineKeyboardButton("📱 Social Media", callback_data="style_social")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎨 Choose your video style:",
        reply_markup=reply_markup
    )

async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT prompts_refined FROM telegram_users WHERE telegram_id = %s",
            (str(user.id),)
        )
        result = cursor.fetchone()
        cursor.close()
        connection.close()

        if result:
            prompts = result[0] or 0
            await update.message.reply_text(
                f"📊 Your Afrigen Stats\n\n"
                f"✨ Prompts Refined: {prompts}\n\n"
                f"Keep creating African content! 🌍\n\n"
                f"Africa Creates, AI Generates 🇳🇬"
            )
        else:
            await update.message.reply_text(
                "📊 No stats yet!\n\nSend /start to get started! 🚀"
            )
    except Exception as e:
        await update.message.reply_text("❌ Error fetching stats!")
        print(f"Credits error: {e}")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 Prompt History\n\n"
        "🔜 History feature coming soon!\n\n"
        "For now use /credits to see your stats!\n\n"
        "Africa Creates, AI Generates 🌍"
    )

async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_video":
        context.user_data['mode'] = 'video'
        await query.edit_message_text(
            "🎬 Video Prompt Mode activated!\n\n"
            "Type your video idea and I'll refine it!\n\n"
            "Example: 'A Nigerian king in Lagos'"
        )
        return

    elif data == "menu_image":
        context.user_data['mode'] = 'image'
        await query.edit_message_text(
            "🖼️ Image Prompt Mode activated!\n\n"
            "Type your image idea and I'll refine it!\n\n"
            "Example: 'A Yoruba queen in traditional attire'"
        )
        return

    elif data == "menu_help":
        await query.edit_message_text(
            "❓ Afrigen Bot Help\n\n"
            "Commands:\n"
            "/start - Main menu\n"
            "/styles - Choose style\n"
            "/credits - Check stats\n\n"
            "How to use:\n"
            "1. Choose Video or Image mode\n"
            "2. Choose your style\n"
            "3. Type your idea\n"
            "4. Get refined prompt!\n\n"
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
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🎨 Choose your style:",
            reply_markup=reply_markup
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
        f"Now type your idea and I'll refine it!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("handle_message called!")
    user_prompt = update.message.text
    style = context.user_data.get('style', 'cinematic')
    mode = context.user_data.get('mode', 'video')

    await update.message.chat.send_action("typing")
    await update.message.reply_text("⏳ Refining your prompt with AI...")

    try:
        if mode == 'image':
            refined = refine_image_prompt(user_prompt, style)
            mode_text = "Image"
        else:
            refined = refine_prompt(user_prompt, style)
            mode_text = "Video"

        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE telegram_users SET prompts_refined = prompts_refined + 1 WHERE telegram_id = %s",
                (str(update.effective_user.id),)
            )
            connection.commit()
            cursor.close()
            connection.close()
        except Exception as e:
            print(f"DB update error: {e}")

        keyboard = [
            [InlineKeyboardButton("🎬 Video Prompt", callback_data="menu_video"),
             InlineKeyboardButton("🖼️ Image Prompt", callback_data="menu_image")],
            [InlineKeyboardButton("🎨 Choose Style", callback_data="menu_styles"),
             InlineKeyboardButton("❓ Help", callback_data="menu_help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✨ AI Refined {mode_text} Prompt:\n\n"
            f"{refined}\n\n"
            f"─────────────────\n"
            f"📋 Copy and use this prompt!\n"
            f"🚀 Full platform launching soon!\n\n"
            f"Africa Creates, AI Generates 🌍",
            reply_markup=reply_markup
        )

    except Exception as e:
        await update.message.reply_text(
            "❌ Sorry, something went wrong!\n"
            "Please try again later."
        )
        logger.error(f"Error: {e}")

def run_bot():
    try:
        print("🚀 Starting bot...")

        print("TOKEN:", bool(TOKEN))

        PORT = int(os.environ.get("PORT", 10000))
        print("PORT:", PORT)

        app = Application.builder().token(TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("styles", styles_command))
        app.add_handler(CommandHandler("credits", credits_command))
        app.add_handler(CommandHandler("history", history_command))
        app.add_handler(CallbackQueryHandler(handle_style_selection))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        print("🤖 Starting webhook server...")

        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url="https://afrigen-bot.onrender.com",
            secret_token="afrigen_secret"
        )

    except Exception as e:
        import traceback

        print("❌ FULL ERROR:")
        traceback.print_exc()