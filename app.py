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


load_dotenv()
app = Flask(__name__)
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

@scheduler.task('cron', id='reset_credits', day=1, hour=0)
def reset_monthly_credits():
    with app.app_context():
        from models import User
        free_users = User.query.filter_by(plan='free').all()
        for user in free_users:
            user.credits = 5
        db.session.commit()
        print("✅ Monthly credits reset for all free users!")

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
    from bot.bot import start, help_command, styles_command, credits_command, history_command, handle_style_selection, \
        handle_message
    from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("styles", styles_command))
    telegram_app.add_handler(CommandHandler("credits", credits_command))
    telegram_app.add_handler(CommandHandler("history", history_command))
    telegram_app.add_handler(CallbackQueryHandler(handle_style_selection))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await telegram_app.initialize()
    print("Telegram webhook bot ready!")

with app.app_context():
    db.create_all()
    print("Afrigen database ready")

if __name__ == '__main__':
    app.run(debug=True)
