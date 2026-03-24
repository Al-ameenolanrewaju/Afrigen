import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


from groq import Groq


groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def refine_prompt(user_prompt, style="cinematic"):
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": f"You are an African video prompt engineer. Refine this {style} video prompt into a detailed cinematic description. Keep under 200 words. Return ONLY the prompt."},
            {"role": "user", "content": f"Refine: {user_prompt}"}
        ],
        max_tokens=300
    )
    return response.choices[0].message.content


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Save to database
    try:
        import mysql.connector
        connection = mysql.connector.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "afrigen")
        )
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
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"DB error: {e}")

    # Main menu keyboard
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
    """Help message"""
    await update.message.reply_text(
        "🎬 Afrigen Bot Help\n\n"
        "How to use:\n"
        "1. Type your video idea\n"
        "2. Bot refines it with AI\n"
        "3. Use refined prompt to generate video!\n\n"
        "Example:\n"
        "You type: 'Nigerian man in Lagos'\n"
        "Bot returns: Professional cinematic prompt!\n\n"
        "Visit afrigen.co for full video generation! 🚀"
    )


async def styles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available styles"""
    keyboard = [
        [InlineKeyboardButton("🎬 Cinematic", callback_data="style_cinematic")],
        [InlineKeyboardButton("🎌 Anime", callback_data="style_anime")],
        [InlineKeyboardButton("🌍 Realistic", callback_data="style_realistic")],
        [InlineKeyboardButton("👑 African", callback_data="style_african")],
        [InlineKeyboardButton("📱 Social Media", callback_data="style_social")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🎬 Choose your video style:",
        reply_markup=reply_markup
    )


async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # Handle main menu buttons
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
            "/styles - Choose video style\n"
            "/credits - Check your credits\n"
            "/history - See past prompts\n\n"
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

    # Handle style selection
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
    mode = context.user_data.get('mode', 'video')  # ← get mode!

    await update.message.chat.send_action("typing")
    await update.message.reply_text("⏳ Refining your prompt with AI...")

    try:
        # Refine based on mode
        if mode == 'image':
            from services.claude import refine_image_prompt
            refined = refine_image_prompt(user_prompt, style)
            mode_emoji = "🖼️"
            mode_text = "Image"
        else:
            refined = refine_prompt(user_prompt, style)
            mode_emoji = "🎬"
            mode_text = "Video"

        # Update prompts count
        try:
            import mysql.connector
            connection = mysql.connector.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                user=os.environ.get("DB_USER", "root"),
                password=os.environ.get("DB_PASSWORD", ""),
                database=os.environ.get("DB_NAME", "afrigen")
            )
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

        # Show main menu again
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


async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's prompt count"""
    user = update.effective_user

    try:
        import mysql.connector
        connection = mysql.connector.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "afrigen")
        )
        cursor = connection.cursor()
        cursor.execute(
            "SELECT prompts_refined FROM telegram_users WHERE telegram_id = %s",
            (str(user.id),)
        )
        result = cursor.fetchone()
        cursor.close()
        connection.close()

        if result:
            prompts = result[0]
            await update.message.reply_text(
                f"📊 Your Afrigen Stats\n\n"
                f"✨ Prompts Refined: {prompts or 0}\n\n"
                f"Keep creating African content! 🌍\n\n"
                f"Africa Creates, AI Generates 🇳🇬"
            )
        else:
            await update.message.reply_text(
                "📊 No stats yet!\n\n"
                "Send /start to get started! 🚀"
            )
    except Exception as e:
        await update.message.reply_text("❌ Error fetching stats!")
        print(f"Credits error: {e}")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's prompt history"""
    await update.message.reply_text(
        "📜 Prompt History\n\n"
        "Your recent prompts:\n\n"
        "🔜 History feature coming soon!\n\n"
        "For now use /credits to see your stats!\n\n"
        "Africa Creates, AI Generates 🌍"
    )


def run_bot():
    """Run the Telegram bot"""
    app = Application.builder().token(TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("styles", styles_command))
    app.add_handler(CommandHandler("credits", credits_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CallbackQueryHandler(handle_style_selection))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 AfrigenBot is running!")
    app.run_polling()


if __name__ == "__main__":
    run_bot()