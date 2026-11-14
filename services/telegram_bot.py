import os
import re
import html
import json
import logging
import tempfile
import threading
import requests
from datetime import datetime, timezone
from flask import current_app
from models import db, User, TelegramUser, Generation
from services.credits import video_gate, image_gate, charge_video, charge_image, is_paid_plan, get_tier
from services.video import generate_image, generate_video, add_text_overlay, add_watermark_to_video, merge_audio_into_video
from services.claude import refine_prompt, refine_image_prompt, extract_on_screen_text

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

STYLE_NAMES = {
    "cinematic": "🎬 Cinematic",
    "anime": "🎌 Anime",
    "realistic": "🌍 Realistic",
    "african": "👑 African Cultural",
    "social": "📱 Social Media / TikTok",
    "movie": "🎥 Movie Scene",
}

STYLE_DESCRIPTIONS = {
    "cinematic": "Hollywood-grade shots with cinematic lighting",
    "anime": "Japanese anime aesthetic with African characters",
    "realistic": "Photorealistic African photography",
    "african": "Rich traditional African cultural scenes",
    "social": "Viral social media content for TikTok/Instagram",
    "movie": "Cinematic long-form movie scene (Director/Studio only)",
}


class TelegramBotService:
    def __init__(self, token=None):
        self._token = token

    @property
    def token(self):
        return self._token or os.environ.get("TELEGRAM_BOT_TOKEN")

    @property
    def is_configured(self):
        return bool(self.token)

    def _api_url(self, method):
        return f"{TELEGRAM_API_BASE}{self.token}/{method}"

    def call_api(self, method, payload=None, files=None, timeout=30):
        if not self.is_configured:
            logger.warning("Telegram Bot Token is not configured.")
            return None
        url = self._api_url(method)
        try:
            if files:
                resp = requests.post(url, data=payload, files=files, timeout=timeout)
            else:
                resp = requests.post(url, json=payload, timeout=timeout)
            try:
                data = resp.json()
            except Exception:
                data = {"ok": False, "raw_response": resp.text[:300]}
            if not data.get("ok"):
                logger.error("Telegram API response error for %s (status %s): %s | %s", method, resp.status_code, data.get("description"), resp.text[:300])
            return data
        except Exception as e:
            logger.error("Telegram API HTTP error (%s): %s", method, e)
            return None

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        res = self.call_api("sendMessage", payload)
        # If HTML parsing failed, retry as plain text so the user still receives the message
        if not res or not res.get("ok"):
            if parse_mode == "HTML":
                payload["parse_mode"] = None
                res = self.call_api("sendMessage", payload)
        return res

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self.call_api("editMessageText", payload)

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        return self.call_api("answerCallbackQuery", payload)

    def send_chat_action(self, chat_id, action="typing"):
        return self.call_api("sendChatAction", {"chat_id": chat_id, "action": action})

    def send_photo(self, chat_id, photo_url, caption=None, reply_markup=None):
        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "parse_mode": "HTML"
        }
        if caption:
            payload["caption"] = caption
        if reply_markup:
            payload["reply_markup"] = reply_markup
        res = self.call_api("sendPhoto", payload, timeout=60)
        if res and res.get("ok"):
            return res

        # Fallback 1: Retry without HTML parsing
        payload["parse_mode"] = None
        res = self.call_api("sendPhoto", payload, timeout=60)
        if res and res.get("ok"):
            return res

        # Fallback 2: Stream bytes directly
        try:
            r = requests.get(photo_url, timeout=45)
            if r.status_code == 200:
                files = {"photo": ("photo.jpg", r.content, "image/jpeg")}
                upload_payload = {"chat_id": chat_id}
                if caption:
                    upload_payload["caption"] = re.sub(r'<[^>]*>', '', caption)[:1024]
                res = self.call_api("sendPhoto", payload=upload_payload, files=files, timeout=60)
                if res and res.get("ok"):
                    return res
        except Exception as e:
            logger.warning("Direct photo upload failed: %s", e)

        # Fallback 3: Send photo URL directly in message
        return self.send_message(
            chat_id,
            f"🖼️ <b>Your photo is ready!</b>\n\n<a href='{photo_url}'>Click here to view &amp; download your photo</a>",
            reply_markup=reply_markup
        )

    def send_video(self, chat_id, video_url, caption=None, reply_markup=None):
        payload = {
            "chat_id": chat_id,
            "video": video_url,
            "parse_mode": "HTML"
        }
        if caption:
            payload["caption"] = caption
        if reply_markup:
            payload["reply_markup"] = reply_markup
        res = self.call_api("sendVideo", payload, timeout=60)
        if res and res.get("ok"):
            return res

        # Fallback 1: Retry without HTML parsing
        payload["parse_mode"] = None
        res = self.call_api("sendVideo", payload, timeout=60)
        if res and res.get("ok"):
            return res

        # Fallback 2: Download video bytes and upload directly to Telegram
        try:
            logger.info("Downloading video bytes from %s for direct Telegram upload", video_url)
            r = requests.get(video_url, timeout=90)
            if r.status_code == 200:
                files = {"video": ("video.mp4", r.content, "video/mp4")}
                upload_payload = {"chat_id": chat_id}
                if caption:
                    upload_payload["caption"] = re.sub(r'<[^>]*>', '', caption)[:1024]
                res = self.call_api("sendVideo", payload=upload_payload, files=files, timeout=180)
                if res and res.get("ok"):
                    return res
        except Exception as e:
            logger.warning("Direct video upload to Telegram failed: %s", e)

        # Fallback 3: Send direct clickable video link so user ALWAYS gets it!
        return self.send_message(
            chat_id,
            f"🎬 <b>Your video is ready!</b>\n\n<a href='{video_url}'>Click here to watch &amp; download your video</a>",
            reply_markup=reply_markup
        )

    def download_file(self, file_id, dest_path):
        res = self.call_api("getFile", {"file_id": file_id})
        if not res or not res.get("result"):
            raise ValueError(f"Could not retrieve file information for {file_id}")
        file_path = res["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 32):
                    f.write(chunk)
        return dest_path

    def set_webhook(self, webhook_url, secret_token=None):
        payload = {
            "url": webhook_url,
            "drop_pending_updates": True,
            "allowed_updates": ["message", "edited_message", "callback_query"]
        }
        if secret_token:
            payload["secret_token"] = secret_token
        return self.call_api("setWebhook", payload)

    def get_webhook_info(self):
        return self.call_api("getWebhookInfo")

    # ---------- UI Keyboards ----------

    def main_menu_keyboard(self, user=None):
        """Main menu — adds Movie Scene for Director/Studio users."""
        rows = [
            [
                {"text": "🎬 Make Video", "callback_data": "menu_video"},
                {"text": "🖼️ Make Photo", "callback_data": "menu_image"}
            ],
            [
                {"text": "🎨 Styles", "callback_data": "menu_styles"},
                {"text": "💳 Plan & Credits", "callback_data": "menu_credits"}
            ],
            [
                {"text": "📋 My History", "callback_data": "menu_history"},
                {"text": "❓ Help", "callback_data": "menu_help"}
            ]
        ]
        return {"inline_keyboard": rows}

    def styles_keyboard(self, user=None):
        """Style keyboard — shows Movie Scene only for Director/Studio tier."""
        rows = [
            [
                {"text": "🎬 Cinematic", "callback_data": "style_cinematic"},
                {"text": "🎌 Anime", "callback_data": "style_anime"}
            ],
            [
                {"text": "🌍 Realistic", "callback_data": "style_realistic"},
                {"text": "👑 African", "callback_data": "style_african"}
            ],
            [
                {"text": "📱 Social Media", "callback_data": "style_social"}
            ],
        ]
        # Movie Scene only for Director / Studio tier
        tier = get_tier(getattr(user, "plan", "free") if user else "free") if user else 0
        if tier >= 2:
            rows.append([{"text": "🎥 Movie Scene (Studio/Director)", "callback_data": "style_movie"}])

        rows.append([{"text": "⬅️ Back to Menu", "callback_data": "menu_main"}])
        return {"inline_keyboard": rows}

    def duration_keyboard(self):
        """Ask user to choose video duration."""
        return {
            "inline_keyboard": [
                [
                    {"text": "⚡ 5 Seconds", "callback_data": "dur_5"},
                    {"text": "🎞️ 10 Seconds", "callback_data": "dur_10"}
                ],
                [{"text": "❌ Cancel", "callback_data": "dur_cancel"}]
            ]
        }

    def voiceover_keyboard(self):
        """Ask user whether to add a Nigerian voiceover."""
        return {
            "inline_keyboard": [
                [
                    {"text": "🔊 Add Voiceover", "callback_data": "vo_yes"},
                    {"text": "🔇 Silent Video", "callback_data": "vo_no"}
                ],
                [{"text": "❌ Cancel", "callback_data": "vo_cancel"}]
            ]
        }

    def aspect_ratio_keyboard(self):
        """Let users pick aspect ratio for images."""
        return {
            "inline_keyboard": [
                [
                    {"text": "⬜ Square 1:1", "callback_data": "ar_1:1"},
                    {"text": "🖥️ Landscape 16:9", "callback_data": "ar_16:9"}
                ],
                [
                    {"text": "📱 Portrait 9:16", "callback_data": "ar_9:16"},
                    {"text": "❌ Cancel", "callback_data": "ar_cancel"}
                ]
            ]
        }

    # ---------- User State Management ----------

    def get_or_create_user(self, from_user, chat=None):
        tg_id = str(from_user.get("id"))
        username = ((from_user.get("username") or "").strip()[:80]) or None
        first_name = ((from_user.get("first_name") or "").strip()[:80]) or None
        chat_id = str(chat.get("id")) if chat else tg_id
        chat_title = ((chat.get("title") or "").strip()[:255]) or None if chat else None

        try:
            tg_user = TelegramUser.query.filter_by(telegram_id=tg_id).first()
        except Exception:
            db.session.rollback()
            tg_user = None

        try:
            if not tg_user:
                tg_user = TelegramUser(
                    telegram_id=tg_id,
                    username=username,
                    first_name=first_name,
                    chat_id=chat_id,
                    chat_title=chat_title,
                    mode="video",
                    style="cinematic"
                )
                db.session.add(tg_user)
                db.session.commit()
            else:
                updated = False
                if username and tg_user.username != username:
                    tg_user.username = username
                    updated = True
                if first_name and tg_user.first_name != first_name:
                    tg_user.first_name = first_name
                    updated = True
                if chat_id and tg_user.chat_id != chat_id:
                    tg_user.chat_id = chat_id
                    updated = True
                if chat_title and tg_user.chat_title != chat_title:
                    tg_user.chat_title = chat_title
                    updated = True
                if updated:
                    db.session.commit()
        except Exception:
            db.session.rollback()

        return tg_user

    def link_account(self, tg_user, code):
        clean_code = (code or "").strip().upper()
        if not clean_code:
            return False, "Please provide your 6-character connection code, e.g. <code>/link ABC123</code>"

        user = User.query.filter_by(telegram_link_code=clean_code).first()
        if not user:
            return False, "❌ Invalid or expired connection code. Please generate a new code on your Afrigen dashboard."

        tg_user.user_id = user.id
        user.telegram_link_code = None
        db.session.commit()
        return True, f"🎉 <b>Success!</b> Your Telegram account is now connected to <b>{user.username}</b> ({user.plan.upper()} Plan)."

    # ---------- Pending Generation Session Storage ----------
    # Stored in-memory per tg_user.id; tiny footprint, non-critical.
    _pending_generations: dict = {}

    def _store_pending(self, tg_user_id, data: dict):
        TelegramBotService._pending_generations[tg_user_id] = data

    def _pop_pending(self, tg_user_id) -> dict:
        return TelegramBotService._pending_generations.pop(tg_user_id, {})

    def _get_pending(self, tg_user_id) -> dict:
        return TelegramBotService._pending_generations.get(tg_user_id, {})

    # ---------- Update Processing ----------

    def process_update(self, update_data, flask_app=None):
        if not update_data or not isinstance(update_data, dict):
            return

        # 1. Handle Callback Query (inline button clicks)
        if "callback_query" in update_data:
            self._handle_callback_query(update_data["callback_query"], flask_app=flask_app)
            return

        # 2. Handle Message
        message = update_data.get("message")
        if not message:
            return

        from_user = message.get("from", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if not from_user or not chat_id:
            return

        tg_user = self.get_or_create_user(from_user, chat)
        text = (message.get("text") or "").strip()

        # Handle Commands
        if text.startswith("/"):
            self._handle_command(tg_user, text, chat_id)
            return

        # Handle Voice / Audio Notes
        voice_or_audio = message.get("voice") or message.get("audio")
        if voice_or_audio:
            self._handle_voice_message(tg_user, voice_or_audio, chat_id, flask_app)
            return

        # Handle Text Generation Prompts
        if text:
            self._handle_text_prompt(tg_user, text, chat_id, flask_app)

    def _handle_command(self, tg_user, text, chat_id):
        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]
        arg = parts[1].strip() if len(parts) > 1 else ""

        if command == "/start":
            if arg:
                # Deep link with connection code (/start <code>)
                ok, msg = self.link_account(tg_user, arg)
                self.send_message(chat_id, msg, reply_markup=self.main_menu_keyboard(tg_user.user))
                return

            user = tg_user.user
            if user:
                tier = get_tier(user.plan)
                plan_tips = {
                    0: "You have <b>2 free images/month</b>. Upgrade for unlimited video & image generation!",
                    1: f"You have <b>{user.credits or 0} credits</b>. Use them for videos &amp; photos!",
                    2: f"You have <b>{user.credits or 0} credits</b> + Image-to-Video unlocked!",
                    3: f"You have <b>{user.credits or 0} credits</b> + Movie Scene Studio + Priority generation!",
                }
                status_text = (
                    f"✅ <b>Connected:</b> {html.escape(user.username)} "
                    f"(<b>{user.plan.upper()}</b> Plan)\n"
                    f"💡 {plan_tips.get(tier, '')}"
                )
            else:
                status_text = (
                    "🔗 <b>Account Not Connected Yet</b>\n"
                    "Link your account to access your credits &amp; full generation powers."
                )

            welcome = (
                f"👋 <b>Welcome to Afrigen AI, {html.escape(tg_user.first_name or 'Creator')}!</b>\n\n"
                "<i>Africa Creates, AI Generates 🌍</i>\n\n"
                f"{status_text}\n\n"
                "🎬 Tap <b>Make Video</b> or <b>Make Photo</b>, then type your idea "
                "or 🎙️ record a voice note!"
            )
            self.send_message(chat_id, welcome, reply_markup=self.main_menu_keyboard(user))

        elif command == "/link":
            if not arg:
                self.send_message(
                    chat_id,
                    "ℹ️ <b>How to Link Your Afrigen Account:</b>\n\n"
                    "1. Visit <a href='https://afrigen.com.ng/dashboard'>afrigen.com.ng/dashboard</a>\n"
                    "2. Click <b>Connect Telegram</b> to get your 6-character code\n"
                    "3. Send <code>/link &lt;code&gt;</code> here.\n\n"
                    "<i>All plans, including free, have full bot access!</i>"
                )
                return
            ok, msg = self.link_account(tg_user, arg)
            self.send_message(chat_id, msg, reply_markup=self.main_menu_keyboard(tg_user.user))

        elif command == "/credits":
            self._send_credits_info(tg_user, chat_id)

        elif command == "/styles":
            self.send_message(
                chat_id,
                f"🎨 <b>Choose Your Generation Style</b>\nCurrent style: <b>{STYLE_NAMES.get(tg_user.style, tg_user.style)}</b>",
                reply_markup=self.styles_keyboard(tg_user.user)
            )

        elif command == "/help":
            self._send_help_info(chat_id, tg_user.user)

        elif command == "/history":
            self._send_history(tg_user, chat_id)

    def _send_credits_info(self, tg_user, chat_id):
        if not tg_user.user:
            self.send_message(
                chat_id,
                "💳 <b>No Linked Account</b>\n\n"
                "Connect your Afrigen account to check your credits balance.\n"
                "Visit <a href='https://afrigen.com.ng/dashboard'>afrigen.com.ng</a> to link.",
                reply_markup=self.main_menu_keyboard()
            )
            return

        user = tg_user.user
        free_videos = getattr(user, 'free_video_allowance', 0) or 0
        tier = get_tier(user.plan)

        info = (
            f"👤 <b>Afrigen Account:</b> {html.escape(user.username)}\n"
            f"⭐ <b>Plan:</b> {user.plan.upper()}\n"
        )

        if not is_paid_plan(user.plan):
            images_used = user.monthly_images_used or 0
            info += (
                f"\n📊 <b>Free Tier Allowances:</b>\n"
                f"🖼️ Monthly Free Images: <b>{images_used}/2 used</b>\n"
                f"🎁 Free Video Tokens: <b>{free_videos}</b>\n"
                f"🪙 Account Credits: <b>{user.credits or 0}</b>\n\n"
                "ℹ️ <i>You receive 2 free photos every month. Once your free quota is used, "
                "any remaining credits (2 credits/image) will automatically power your next generations.</i>\n\n"
                "👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade Plan</a> for expanded video access and daily credits."
            )
        else:
            info += f"🪙 <b>Credits:</b> {user.credits or 0}\n"
            if tier >= 2:
                info += "🎥 <b>Image-to-Video:</b> Unlocked ✅\n"
            if tier >= 3:
                info += "🎬 <b>Movie Scene Studio:</b> Unlocked ✅\n"
            info += f"\n✅ Full <b>{user.plan.upper()}</b> access active!"

        self.send_message(chat_id, info, reply_markup=self.main_menu_keyboard(user))

    def _send_help_info(self, chat_id, user=None):
        tier = get_tier(getattr(user, "plan", "free") if user else "free")
        help_text = (
            "💡 <b>Afrigen Bot — Complete Guide</b>\n\n"
            "<b>📋 Commands:</b>\n"
            "• /start — Main menu &amp; account status\n"
            "• /link &lt;code&gt; — Connect your website account\n"
            "• /credits — Check balance &amp; plan details\n"
            "• /styles — Change visual style\n"
            "• /history — Your last 5 generations\n"
            "• /help — Show this guide\n\n"
            "<b>🎨 How to Generate:</b>\n"
            "1. Tap <b>Make Video</b> or <b>Make Photo</b>\n"
            "2. Choose your <b>Style</b> (Cinematic, Realistic, etc.)\n"
            "3. Type your idea or 🎙️ send a <b>voice note</b>\n"
            "4. For paid users: choose <b>duration</b> &amp; optional <b>voiceover</b>\n"
            "5. AI refines your prompt → delivers media directly here!\n\n"
            "<b>🔊 Voiceover:</b> Paid users can add a free Nigerian English AI voice to any video!\n\n"
        )
        if tier >= 2:
            help_text += (
                "<b>🎥 Movie Scene Studio:</b> Generate long-form cinematic scenes "
                "using Afrigen Movie Engine. Available via Styles menu.\n\n"
            )
        help_text += "<i>Africa Creates, AI Generates 🌍</i>"
        self.send_message(chat_id, help_text, reply_markup=self.main_menu_keyboard(user))

    def _send_history(self, tg_user, chat_id):
        if not tg_user.user:
            self.send_message(
                chat_id,
                "📋 <b>No linked account.</b> Connect your Afrigen account to view history.",
                reply_markup=self.main_menu_keyboard()
            )
            return

        try:
            gens = (
                Generation.query
                .filter_by(user_id=tg_user.user.id)
                .order_by(Generation.created_at.desc())
                .limit(5)
                .all()
            )
        except Exception:
            gens = []

        if not gens:
            self.send_message(
                chat_id,
                "📋 <b>No generations yet.</b>\nTap <b>Make Video</b> or <b>Make Photo</b> to create your first!",
                reply_markup=self.main_menu_keyboard(tg_user.user)
            )
            return

        lines = ["📋 <b>Your Last 5 Generations:</b>\n"]
        for i, gen in enumerate(gens, 1):
            emoji = "🎬" if gen.generation_type == "video" else "🖼️"
            status_icon = "✅" if gen.status == "completed" else "❌"
            prompt_preview = html.escape((gen.original_prompt or "")[:60])
            ts = ""
            if gen.created_at:
                ts = gen.created_at.strftime("%b %d, %H:%M")
            url_part = ""
            if gen.status == "completed":
                url = gen.video_url or gen.image_url or ""
                if url:
                    url_part = f" — <a href='{url}'>View</a>"
            lines.append(f"{i}. {emoji} {status_icon} <i>{prompt_preview}</i> <code>{ts}</code>{url_part}")

        self.send_message(chat_id, "\n".join(lines), reply_markup=self.main_menu_keyboard(tg_user.user))

    def _handle_callback_query(self, query, flask_app=None):
        query_id = query.get("id")
        data = query.get("data", "")
        message = query.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        from_user = query.get("from", {})

        self.answer_callback_query(query_id)
        if not chat_id:
            return

        tg_user = self.get_or_create_user(from_user, message.get("chat"))
        user = tg_user.user

        if data == "menu_video":
            tg_user.mode = "video"
            db.session.commit()
            self.edit_message_text(
                chat_id, message_id,
                "🎬 <b>Video Mode Active!</b>\n\n"
                f"Style: <b>{STYLE_NAMES.get(tg_user.style, tg_user.style)}</b>\n\n"
                "🎙️ Send your idea as text or voice note to begin!",
                reply_markup=self.main_menu_keyboard(user)
            )

        elif data == "menu_image":
            tg_user.mode = "image"
            db.session.commit()
            self.edit_message_text(
                chat_id, message_id,
                "🖼️ <b>Photo Mode Active!</b>\n\n"
                f"Style: <b>{STYLE_NAMES.get(tg_user.style, tg_user.style)}</b>\n\n"
                "✍️ Describe your photo and I'll bring it to life!",
                reply_markup=self.main_menu_keyboard(user)
            )

        elif data == "menu_styles":
            self.edit_message_text(
                chat_id, message_id,
                f"🎨 <b>Choose Your Visual Style:</b>\n\nCurrent: <b>{STYLE_NAMES.get(tg_user.style, tg_user.style)}</b>",
                reply_markup=self.styles_keyboard(user)
            )

        elif data == "menu_credits":
            self._send_credits_info(tg_user, chat_id)

        elif data == "menu_help":
            self._send_help_info(chat_id, user)

        elif data == "menu_history":
            self._send_history(tg_user, chat_id)

        elif data == "menu_main":
            self.edit_message_text(
                chat_id, message_id,
                "🌍 <b>Afrigen AI — Africa Creates, AI Generates</b>\n\nSelect an option or send your prompt:",
                reply_markup=self.main_menu_keyboard(user)
            )

        elif data.startswith("style_"):
            style_key = data.replace("style_", "")
            # Guard movie style to Director/Studio only
            if style_key == "movie" and get_tier(getattr(user, "plan", "free") if user else "free") < 2:
                self.send_message(
                    chat_id,
                    "🎥 <b>Movie Scene Studio</b> requires a <b>Studio or Director</b> plan.\n\n"
                    "👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade your plan</a>",
                    reply_markup=self.main_menu_keyboard(user)
                )
                return
            tg_user.style = style_key
            db.session.commit()
            style_label = STYLE_NAMES.get(style_key, style_key)
            desc = STYLE_DESCRIPTIONS.get(style_key, "")
            self.edit_message_text(
                chat_id, message_id,
                f"✅ Style set to: <b>{style_label}</b>\n"
                f"<i>{desc}</i>\n\n"
                f"Ready in <b>{tg_user.mode.upper()}</b> mode. Send your idea now!",
                reply_markup=self.main_menu_keyboard(user)
            )

        # --- Duration callbacks ---
        elif data in ("dur_5", "dur_10", "dur_cancel"):
            pending = self._get_pending(tg_user.id)
            if not pending or pending.get("step") != "await_duration":
                self.send_message(chat_id, "⏰ This prompt session has expired. Please send your prompt again.", reply_markup=self.main_menu_keyboard(user))
                return
            if data == "dur_cancel":
                self._pop_pending(tg_user.id)
                self.edit_message_text(chat_id, message_id, "❌ Generation cancelled.", reply_markup=self.main_menu_keyboard(user))
                return
            duration = "5" if data == "dur_5" else "10"
            pending["duration"] = duration
            pending["step"] = "await_voiceover"
            self._store_pending(tg_user.id, pending)
            self.edit_message_text(
                chat_id, message_id,
                f"🎞️ <b>{duration}-second video selected!</b>\n\n"
                "🔊 Would you like to add an AI Nigerian English voiceover to your video?\n"
                "<i>(Free Microsoft Neural TTS — no extra credits)</i>",
                reply_markup=self.voiceover_keyboard()
            )

        # --- Voiceover callbacks ---
        elif data in ("vo_yes", "vo_no", "vo_cancel"):
            pending = self._get_pending(tg_user.id)
            if not pending or pending.get("step") != "await_voiceover":
                self.send_message(chat_id, "⏰ This prompt session has expired. Please send your prompt again.", reply_markup=self.main_menu_keyboard(user))
                return
            if data == "vo_cancel":
                self._pop_pending(tg_user.id)
                self.edit_message_text(chat_id, message_id, "❌ Generation cancelled.", reply_markup=self.main_menu_keyboard(user))
                return
            pending["voiceover"] = (data == "vo_yes")
            pending["step"] = "ready"
            self._pop_pending(tg_user.id)

            # Edit message to show we're starting
            vo_label = "with Nigerian AI voiceover 🔊" if pending["voiceover"] else "silent 🔇"
            self.edit_message_text(
                chat_id, message_id,
                f"🚀 <b>Starting generation...</b>\n"
                f"Duration: <b>{pending['duration']}s</b> · {vo_label}\n\n"
                "<i>This usually takes 1-3 minutes. I'll ping you when it's ready!</i>"
            )

            # Launch generation in background
            app = getattr(self, "_flask_app", None) or current_app._get_current_object()
            tg_user_id = tg_user.id
            prompt_text = pending["prompt"]
            duration = pending["duration"]
            voiceover = pending["voiceover"]
            style = pending.get("style", tg_user.style)

            def _worker():
                with app.app_context():
                    self._execute_generation(
                        tg_user_id, chat_id, prompt_text,
                        duration=duration, voiceover=voiceover, style_override=style
                    )
            threading.Thread(target=_worker, daemon=True).start()

        # --- Aspect ratio callbacks (image mode) ---
        elif data.startswith("ar_"):
            pending = self._get_pending(tg_user.id)
            if not pending or pending.get("step") != "await_aspect_ratio":
                self.send_message(chat_id, "⏰ This prompt session has expired. Please send your prompt again.", reply_markup=self.main_menu_keyboard(user))
                return
            if data == "ar_cancel":
                self._pop_pending(tg_user.id)
                self.edit_message_text(chat_id, message_id, "❌ Generation cancelled.", reply_markup=self.main_menu_keyboard(user))
                return
            ar = data.replace("ar_", "")
            pending["aspect_ratio"] = ar
            pending["step"] = "ready"
            self._pop_pending(tg_user.id)

            ar_labels = {"1:1": "Square 1:1 ⬜", "16:9": "Landscape 16:9 🖥️", "9:16": "Portrait 9:16 📱"}
            self.edit_message_text(
                chat_id, message_id,
                f"🖼️ <b>Generating {ar_labels.get(ar, ar)} image...</b>\n\n"
                "<i>Enhancing your prompt with AI magic... ✨</i>"
            )

            app = getattr(self, "_flask_app", None) or current_app._get_current_object()
            tg_user_id = tg_user.id
            prompt_text = pending["prompt"]
            style = pending.get("style", tg_user.style)

            def _img_worker():
                with app.app_context():
                    self._execute_generation(
                        tg_user_id, chat_id, prompt_text,
                        aspect_ratio=ar, style_override=style
                    )
            threading.Thread(target=_img_worker, daemon=True).start()

    # ---------- Generation Workers ----------

    def _handle_voice_message(self, tg_user, voice_or_audio, chat_id, flask_app):
        file_id = voice_or_audio.get("file_id")
        if not file_id:
            return

        self.send_chat_action(chat_id, "record_voice")
        status_res = self.send_message(chat_id, "🎙️ <i>Transcribing your voice note...</i>")
        status_msg_id = status_res.get("result", {}).get("message_id") if status_res else None

        app = flask_app or current_app._get_current_object()

        def _voice_worker():
            with app.app_context():
                tmp_path = None
                try:
                    fd, tmp_path = tempfile.mkstemp(suffix=".ogg")
                    os.close(fd)
                    self.download_file(file_id, tmp_path)

                    from services.audio import transcribe_voice_note
                    prompt_text = transcribe_voice_note(tmp_path)

                    if not prompt_text or len(prompt_text.strip()) < 3:
                        if status_msg_id:
                            self.edit_message_text(
                                chat_id, status_msg_id,
                                "❌ <i>Couldn't catch your speech clearly. Please speak closer to the mic or type your prompt.</i>"
                            )
                        return

                    if status_msg_id:
                        self.edit_message_text(
                            chat_id, status_msg_id,
                            f"🗣️ <b>Transcribed:</b>\n<i>\"{html.escape(prompt_text)}\"</i>\n\n🚀 Processing your {tg_user.mode} request..."
                        )

                    self._start_generation_flow(tg_user.id, chat_id, prompt_text, flask_app=app)

                except Exception as exc:
                    logger.exception("Voice note transcription failed: %s", exc)
                    self.send_message(chat_id, f"❌ Voice processing failed: {html.escape(str(exc))}")
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass

        threading.Thread(target=_voice_worker, daemon=True).start()

    def _handle_text_prompt(self, tg_user, text, chat_id, flask_app):
        app = flask_app or current_app._get_current_object()
        self._flask_app = app
        self.send_chat_action(chat_id, "typing")
        self._start_generation_flow(tg_user.id, chat_id, text, flask_app=app)

    def _start_generation_flow(self, tg_user_db_id, chat_id, user_prompt, flask_app=None):
        """Decide whether to show interactive options (paid) or go straight to generation (free/basic)."""
        tg_user = db.session.get(TelegramUser, tg_user_db_id)
        if not tg_user:
            return

        # 1. Verify account link
        if not tg_user.user:
            self.send_message(
                chat_id,
                "🔗 <b>Connect Your Afrigen Account First</b>\n\n"
                "To generate AI content, link your Afrigen account:\n"
                "1. Log in at <a href='https://afrigen.com.ng/dashboard'>afrigen.com.ng/dashboard</a>\n"
                "2. Click <b>Connect Telegram</b> to get your 6-character code\n"
                "3. Send <code>/link &lt;code&gt;</code> here.\n\n"
                "<i>All plans, including free, have full bot access!</i>",
                reply_markup=self.main_menu_keyboard()
            )
            return

        user = tg_user.user

        if user.is_banned:
            self.send_message(chat_id, "❌ Your account is currently restricted. Contact support at afrigen.com.ng")
            return

        mode = tg_user.mode or "video"
        style = tg_user.style or "cinematic"
        extended = is_paid_plan(user.plan)

        # 2. Check gate up front before asking for options
        if mode == "image":
            ok, err = image_gate(user)
            if not ok:
                self.send_message(
                    chat_id,
                    f"❌ <b>{html.escape(err)}</b>\n\n"
                    "👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade Plan</a> for unlimited image generation.",
                    reply_markup=self.main_menu_keyboard(user)
                )
                return
        else:
            ok, err, cost = video_gate(user, style, extended=extended)
            if not ok:
                self.send_message(
                    chat_id,
                    f"❌ <b>{html.escape(err)}</b>\n\n"
                    "👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade Plan</a> for unlimited video generation.",
                    reply_markup=self.main_menu_keyboard(user)
                )
                return

        # 3. Interactive duration + voiceover choice for video
        if mode == "video":
            self._store_pending(tg_user.id, {
                "step": "await_duration",
                "prompt": user_prompt,
                "style": style,
            })
            safe_prompt = html.escape(user_prompt[:100])
            self.send_message(
                chat_id,
                f"🎬 <b>Video Options</b>\n\n"
                f"Prompt: <i>\"{safe_prompt}\"</i>\n"
                f"Style: <b>{STYLE_NAMES.get(style, style)}</b>\n\n"
                "⏱️ <b>Choose your video duration:</b>",
                reply_markup=self.duration_keyboard()
            )
            return

        # 4. Image mode — paid users get aspect ratio choice
        if mode == "image" and extended:
            self._store_pending(tg_user.id, {
                "step": "await_aspect_ratio",
                "prompt": user_prompt,
                "style": style,
            })
            safe_prompt = html.escape(user_prompt[:100])
            self.send_message(
                chat_id,
                f"🖼️ <b>Image Options</b>\n\n"
                f"Prompt: <i>\"{safe_prompt}\"</i>\n"
                f"Style: <b>{STYLE_NAMES.get(style, style)}</b>\n\n"
                "📐 <b>Choose aspect ratio:</b>",
                reply_markup=self.aspect_ratio_keyboard()
            )
            return

        # 5. Free users / simple path: generate immediately
        app = getattr(self, "_flask_app", None) or current_app._get_current_object()

        def _worker():
            with app.app_context():
                self._execute_generation(tg_user_db_id, chat_id, user_prompt)

        threading.Thread(target=_worker, daemon=True).start()

    def _execute_generation(
        self,
        tg_user_db_id,
        chat_id,
        user_prompt,
        duration=None,
        voiceover=False,
        aspect_ratio="1:1",
        style_override=None,
    ):
        tg_user = db.session.get(TelegramUser, tg_user_db_id)
        if not tg_user:
            return

        user = tg_user.user
        if not user:
            return

        mode = tg_user.mode or "video"
        style = style_override or tg_user.style or "cinematic"
        has_free_video = (getattr(user, "free_video_allowance", 0) or 0) > 0
        extended = is_paid_plan(user.plan)

        # Determine duration
        if duration is None:
            duration = "10" if extended else "5"

        # 1. Gate check
        if mode == "image":
            ok, err = image_gate(user)
            cost = 0
            if not ok:
                self.send_message(chat_id, f"❌ {html.escape(err)}\n\n👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade Plan</a>")
                return
        else:
            ok, err, cost = video_gate(user, style, extended=extended, duration=duration)
            if not ok:
                self.send_message(chat_id, f"❌ {html.escape(err)}\n\n👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade Plan</a>")
                return

        # 2. Send "working" status
        safe_prompt = html.escape(user_prompt or "")
        status_res = self.send_message(
            chat_id,
            f"🎨 <b>Refining your {mode} idea with AI...</b>\n"
            f"<i>\"{safe_prompt[:100]}\"</i>\n"
            f"Style: {STYLE_NAMES.get(style, style)}"
        )
        status_msg_id = status_res.get("result", {}).get("message_id") if status_res else None
        self.send_chat_action(chat_id, "upload_video" if mode == "video" else "upload_photo")

        # 3. Prompt Refinement
        try:
            if mode == "image":
                refined_prompt = refine_image_prompt(user_prompt, style, user=user)
            else:
                refined_prompt = refine_prompt(
                    user_prompt,
                    style=style,
                    model_name="fal-ai/kling-video/v1/standard/text-to-video",
                    duration=duration,
                    user=user,
                )
        except Exception as e:
            logger.warning("Refine error in bot: %s; using original prompt", e)
            refined_prompt = user_prompt

        if status_msg_id:
            mode_label = "video" if mode == "video" else "photo"
            self.edit_message_text(
                chat_id, status_msg_id,
                f"🚀 <b>Rendering your {mode_label}...</b>\n"
                f"<i>This usually takes 1–3 minutes. Hang tight!</i>"
            )

        # 4. Generate Media
        allow_fal = is_paid_plan(user.plan) or has_free_video
        media_url = None
        error_msg = None

        try:
            if mode == "image":
                provider = "fal" if is_paid_plan(user.plan) else "huggingface"
                res = generate_image(refined_prompt, style=style, aspect_ratio=aspect_ratio, provider=provider, allow_fal=allow_fal)
                if res and res.get("success"):
                    media_url = res.get("image_url")
                else:
                    error_msg = res.get("error") if res else "Image generation returned no result."
            else:
                res = generate_video(
                    refined_prompt,
                    style=style,
                    aspect_ratio="16:9",
                    extended=extended,
                    duration=duration,
                    allow_fal=allow_fal
                )
                if res and res.get("success"):
                    media_url = res.get("video_url")
                else:
                    error_msg = res.get("error") if res else "Video generation returned no result."
        except Exception as exc:
            error_msg = str(exc)

        # 5. Handle Failure
        if not media_url:
            logger.error("Bot generation failed for user %s: %s", user.id, error_msg)
            db.session.add(Generation(
                user_id=user.id,
                original_prompt=user_prompt,
                refined_prompt=refined_prompt,
                generation_type=mode,
                status="failed",
                credit_cost=cost
            ))
            db.session.commit()
            self.send_message(
                chat_id,
                f"❌ <b>Generation Failed</b>\n\n"
                f"<i>{html.escape(error_msg or 'Server busy. Please try again shortly.')}</i>\n\n"
                "🔄 You can try again by sending your prompt again.",
                reply_markup=self.main_menu_keyboard(user)
            )
            return

        # 6. Apply On-Screen Text & Post-processing
        if mode == "video":
            on_screen = extract_on_screen_text(user_prompt)
            if on_screen:
                try:
                    captioned = add_text_overlay(media_url, on_screen)
                    if captioned:
                        media_url = captioned
                except Exception as e:
                    logger.warning("Text overlay error: %s", e)

            # Voiceover (if opted in)
            if voiceover:
                try:
                    if status_msg_id:
                        self.edit_message_text(
                            chat_id, status_msg_id,
                            "🔊 <b>Generating Nigerian AI voiceover...</b>\n<i>Almost there!</i>"
                        )
                    from services.audio import generate_video_script, generate_voiceover
                    script = generate_video_script(user_prompt, style)
                    if script:
                        audio_url = generate_voiceover(script)
                        if audio_url:
                            merged = merge_audio_into_video(media_url, audio_url)
                            if merged:
                                media_url = merged
                except Exception as e:
                    logger.warning("Voiceover error (non-fatal): %s", e)

            # Apply subtle branding watermark for free tier users
            if not is_paid_plan(user.plan):
                try:
                    watermarked = add_watermark_to_video(media_url)
                    if watermarked:
                        media_url = watermarked
                except Exception as e:
                    logger.warning("Watermark error: %s", e)

        # 7. Deduct credits & record completion
        if mode == "image":
            charge_image(user)
            gen = Generation(
                user_id=user.id,
                original_prompt=user_prompt,
                refined_prompt=refined_prompt,
                image_url=media_url,
                generation_type="image",
                status="completed"
            )
        else:
            charge_video(user, cost)
            gen = Generation(
                user_id=user.id,
                original_prompt=user_prompt,
                refined_prompt=refined_prompt,
                video_url=media_url,
                generation_type="video",
                status="completed",
                credit_cost=cost
            )

        db.session.add(gen)
        tg_user.prompts_refined = (tg_user.prompts_refined or 0) + 1
        db.session.commit()

        # 8. Deliver media to user
        safe_prompt_short = html.escape((user_prompt or "")[:120])
        credits_line = ""
        if is_paid_plan(user.plan):
            credits_line = f"🪙 Credits remaining: <b>{user.credits or 0}</b>\n"
        else:
            images_left = max(0, 2 - (user.monthly_images_used or 0))
            if mode == "image":
                credits_line = f"🖼️ Free images left this month: <b>{images_left}</b>\n"
            else:
                credits_line = f"🎁 Free video tokens: <b>{getattr(user, 'free_video_allowance', 0) or 0}</b>\n"

        vo_badge = " 🔊" if voiceover and mode == "video" else ""
        caption = (
            f"✨ <b>Made with Afrigen{vo_badge}</b>\n\n"
            f"Prompt: <i>\"{safe_prompt_short}\"</i>\n"
            f"{credits_line}\n"
            "Africa Creates, AI Generates 🌍"
        )

        sent = False
        try:
            if mode == "image":
                res = self.send_photo(chat_id, media_url, caption=caption, reply_markup=self.main_menu_keyboard(user))
            else:
                res = self.send_video(chat_id, media_url, caption=caption, reply_markup=self.main_menu_keyboard(user))
            if res and res.get("ok"):
                sent = True
        except Exception as e:
            logger.error("Failed to send media to Telegram: %s", e)

        if not sent:
            self.send_message(
                chat_id,
                f"✅ <b>Your {mode} is ready!</b>\n\n"
                f"Prompt: <i>\"{safe_prompt_short}\"</i>\n\n"
                f"🔗 <a href='{media_url}'>Click here to download your {mode}</a>",
                reply_markup=self.main_menu_keyboard(user)
            )


telegram_bot = TelegramBotService()
