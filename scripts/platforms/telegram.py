"""
Post to a Telegram Channel via the Telegram Bot API.

The Telegram channel is a PUBLIC BROADCAST CHANNEL for daily AI prompts.
Each post is ONE actionable AI video prompt extracted from the latest blog post.
This is NOT about blog summaries — it's a unique value proposition:
"Daily AI prompts for Nigerian creators."

Prerequisites:
1. Create a Telegram channel (e.g., @afrigen_ai)
2. Add @AfrigenBot as an administrator of the channel
3. Get the channel ID:
   - Forward a message from the channel to @userinfobot
   - Or send a message to the channel and check:
     GET https://api.telegram.org/bot{TOKEN}/getUpdates
   - The channel ID starts with -100 (e.g., -1001234567890)

Secrets required:
  TELEGRAM_BOT_TOKEN        — From @BotFather
  TELEGRAM_CHANNEL_ID       — The channel ID (e.g., -1001234567890)
  TELEGRAM_ADMIN_CHAT_ID    — Your personal chat ID for admin notifications
"""

import os
import requests


TELEGRAM_API = "https://api.telegram.org"


def post_to_channel(text: str, concise: bool = True) -> dict:
    """Post a message to the Telegram broadcast channel.

    Args:
        text: The formatted message to post.
        concise: Whether the post should be concise.

    Returns:
        {ok: bool, message_id: int|None, error: str|None}
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "")

    if not bot_token or not channel_id:
        return {
            "ok": False,
            "error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID",
            "message_id": None,
        }

    try:
        if concise:
            text = text[:200]  # truncate to 200 characters
        resp = requests.post(
            f"{TELEGRAM_API}/bot{bot_token}/sendMessage",
            json={
                "chat_id": channel_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        data = resp.json()

        if data.get("ok"):
            message_id = data["result"]["message_id"]
            # Build a link to the channel post
            # Channel usernames are in the format @username; channel IDs with -100
            # need the format https://t.me/c/{id_without_-100}/{message_id}
            channel_link = _channel_message_link(channel_id, message_id)
            print(f"[telegram] posted to channel (msg_id={message_id})")
            return {
                "ok": True,
                "message_id": message_id,
                "channel_link": channel_link,
                "error": None,
            }

        error_msg = data.get("description", str(data))
        return {
            "ok": False,
            "error": f"Telegram API error: {error_msg}",
            "message_id": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Telegram exception: {e}",
            "message_id": None,
        }


def notify_admin(report: str) -> dict:
    """Send a distribution report to the admin via Telegram DM.

    Args:
        report: Formatted text report of distribution results.

    Returns:
        {ok: bool, error: str|None}
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    admin_chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")

    if not bot_token or not admin_chat_id:
        return {"ok": False, "error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_CHAT_ID"}

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/bot{bot_token}/sendMessage",
            json={
                "chat_id": admin_chat_id,
                "text": report,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("ok"):
            print("[telegram] admin notified")
            return {"ok": True, "error": None}
        return {"ok": False, "error": data.get("description", str(data))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _channel_message_link(channel_id: str, message_id: int) -> str:
    """Build a link to a specific message in a Telegram channel."""
    # If it's a supergroup/channel ID (starts with -100)
    if channel_id.startswith("-100"):
        clean_id = channel_id[4:]  # Remove -100 prefix
        return f"https://t.me/c/{clean_id}/{message_id}"
    # If it's a username-based channel
    if channel_id.startswith("@"):
        return f"https://t.me/{channel_id[1:]}/{message_id}"
    # Fallback
    return f"https://t.me/c/{channel_id.lstrip('-')}/{message_id}"
