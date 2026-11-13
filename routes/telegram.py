import os
import secrets
import logging
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import csrf, limiter
from models import db, User, TelegramUser
from services.telegram_bot import telegram_bot

logger = logging.getLogger(__name__)

telegram_bp = Blueprint('telegram', __name__, url_prefix='/telegram')


@telegram_bp.route('/webhook', methods=['POST'])
@csrf.exempt
@limiter.exempt
def webhook():
    """Telegram Webhook entrypoint. Telegram pushes update JSON to this endpoint."""
    secret_token = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if secret_token:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header_secret != secret_token:
            logger.warning("Invalid Telegram webhook secret token received.")
            return jsonify({"ok": False, "error": "Unauthorized"}), 403

    update_data = request.get_json(silent=True)
    if not update_data:
        return jsonify({"ok": False, "error": "Empty payload"}), 400

    try:
        telegram_bot.process_update(update_data, flask_app=current_app._get_current_object())
    except Exception as e:
        logger.exception("Error processing Telegram update: %s", e)

    # Telegram requires an immediate 200 OK
    return jsonify({"ok": True}), 200


@telegram_bp.route('/setup-webhook', methods=['GET', 'POST'])
def setup_webhook():
    """One-click utility to register the site's webhook URL with Telegram."""
    base_url = os.environ.get("SITE_URL")
    if not base_url:
        base_url = request.host_url.rstrip('/')
    if not base_url.startswith("http"):
        base_url = f"https://{base_url}"

    # Telegram does not follow HTTP redirects (301/307).
    # afrigen.com.ng redirects to www.afrigen.com.ng, so normalize to www.
    if "afrigen.com.ng" in base_url and "www." not in base_url:
        base_url = base_url.replace("://afrigen.com.ng", "://www.afrigen.com.ng")

    webhook_url = f"{base_url}/telegram/webhook"
    secret_token = os.environ.get("TELEGRAM_WEBHOOK_SECRET") or None

    res = telegram_bot.set_webhook(webhook_url, secret_token=secret_token)
    return jsonify({
        "status": "Webhook registration attempted",
        "registered_url": webhook_url,
        "telegram_response": res
    })


@telegram_bp.route('/webhook-info', methods=['GET'])
def webhook_info():
    """Returns current live Telegram webhook diagnostic info."""
    info = telegram_bot.get_webhook_info()
    return jsonify(info or {"ok": False, "error": "Could not fetch webhook info"})


@telegram_bp.route('/connect-code', methods=['POST'])
@login_required
def connect_code():
    """Generate a 6-character connection code for the user to link their Telegram."""
    code = secrets.token_hex(3).upper()  # e.g., "A8F12C"
    current_user.telegram_link_code = code
    db.session.commit()

    bot_username = os.environ.get("TELEGRAM_BOT_USERNAME", "AfrigenBot").lstrip("@")
    return jsonify({
        "success": True,
        "code": code,
        "bot_username": bot_username,
        "start_url": f"https://t.me/{bot_username}?start={code}"
    })


@telegram_bp.route('/link-status', methods=['GET'])
@login_required
def link_status():
    """Check if the logged-in user has linked their Telegram account."""
    try:
        tg = TelegramUser.query.filter_by(user_id=current_user.id).first()
    except Exception:
        db.session.rollback()
        tg = None
    return jsonify({
        "success": True,
        "linked": tg is not None,
        "telegram_username": tg.username if tg else None,
        "telegram_first_name": tg.first_name if tg else None,
        "mode": getattr(tg, 'mode', 'video') if tg else "video",
        "style": getattr(tg, 'style', 'cinematic') if tg else "cinematic"
    })

