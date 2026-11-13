import os
import re
import json
import logging
import tempfile
import threading
import requests
from datetime import datetime, timezone
from flask import current_app
from models import db, User, TelegramUser, Generation
from services.credits import video_gate, image_gate, charge_video, charge_image
from services.video import generate_image, generate_video, add_text_overlay, add_watermark_to_video
from services.claude import refine_prompt, refine_image_prompt, extract_on_screen_text

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

STYLE_NAMES = {
    "cinematic": "🎬 Cinematic",
    "anime": "🎌 Anime",
    "realistic": "🌍 Realistic",
    "african": "👑 African Cultural",
    "social": "📱 Social Media / TikTok"
}


class TelegramBotService:
    def __init__(self, token=None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")

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
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Telegram API error for %s: %s", method, data.get("description"))
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
        return self.call_api("sendMessage", payload)

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
        return self.call_api("sendPhoto", payload, timeout=60)

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
        return self.call_api("sendVideo", payload, timeout=120)

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

    def main_menu_keyboard(self):
        return {
            "inline_keyboard": [
                [
                    {"text": "🎬 Make Video", "callback_data": "menu_video"},
                    {"text": "🖼️ Make Photo", "callback_data": "menu_image"}
                ],
                [
                    {"text": "🎨 Styles", "callback_data": "menu_styles"},
                    {"text": "💳 Plan & Credits", "callback_data": "menu_credits"}
                ],
                [
                    {"text": "❓ Help", "callback_data": "menu_help"}
                ]
            ]
        }

    def styles_keyboard(self):
        return {
            "inline_keyboard": [
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
                [
                    {"text": "⬅️ Back to Menu", "callback_data": "menu_main"}
                ]
            ]
        }

    # ---------- User State Management ----------

    def get_or_create_user(self, from_user, chat=None):
        tg_id = str(from_user.get("id"))
        tg_user = TelegramUser.query.filter_by(telegram_id=tg_id).first()
        username = from_user.get("username")
        first_name = from_user.get("first_name")
        chat_id = str(chat.get("id")) if chat else tg_id
        chat_title = chat.get("title") if chat else None

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

    # ---------- Update Processing ----------

    def process_update(self, update_data, flask_app=None):
        if not update_data or not isinstance(update_data, dict):
            return

        # 1. Handle Callback Query (inline button clicks)
        if "callback_query" in update_data:
            self._handle_callback_query(update_data["callback_query"])
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
                self.send_message(chat_id, msg, reply_markup=self.main_menu_keyboard())
                return

            status_text = (
                f"✅ Connected to account <b>{tg_user.user.username}</b> ({tg_user.user.plan.upper()} plan)"
                if tg_user.user else
                "🔗 <b>Account Not Connected Yet</b>\nLink your account from the Afrigen dashboard to access your credits & generations."
            )
            welcome = (
                f"👋 <b>Welcome to Afrigen AI, {tg_user.first_name or 'Creator'}!</b>\n\n"
                f"<i>Africa Creates, AI Generates 🌍</i>\n\n"
                f"{status_text}\n\n"
                "Tap <b>Make Video</b> or <b>Make Photo</b>, then send your prompt or record a voice note!"
            )
            self.send_message(chat_id, welcome, reply_markup=self.main_menu_keyboard())

        elif command == "/link":
            if not arg:
                self.send_message(
                    chat_id,
                    "ℹ️ To link your account:\n"
                    "1. Go to <a href='https://afrigen.com.ng/dashboard'>afrigen.com.ng/dashboard</a>\n"
                    "2. Click <b>Connect Telegram</b> to get your 6-character code\n"
                    "3. Send <code>/link &lt;code&gt;</code> here."
                )
                return
            ok, msg = self.link_account(tg_user, arg)
            self.send_message(chat_id, msg, reply_markup=self.main_menu_keyboard())

        elif command == "/credits":
            self._send_credits_info(tg_user, chat_id)

        elif command == "/styles":
            self.send_message(
                chat_id,
                f"🎨 <b>Choose Your Generation Style</b>\nCurrent style: <b>{STYLE_NAMES.get(tg_user.style, tg_user.style)}</b>",
                reply_markup=self.styles_keyboard()
            )

        elif command == "/help":
            self._send_help_info(chat_id)

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
        info = (
            f"👤 <b>Afrigen Account:</b> {user.username}\n"
            f"⭐ <b>Plan:</b> {user.plan.upper()}\n"
            f"🪙 <b>Credits:</b> {user.credits or 0}\n"
        )
        if user.plan == 'free':
            info += f"🎁 <b>Free Video Allowance:</b> {free_videos} video(s)\n"
            info += f"🖼️ <b>Free Images Used:</b> {user.monthly_images_used or 0} / 2\n\n"
            info += "👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade to Pro</a> for unlimited Kling AI videos & daily credits."
        else:
            info += "\n✅ You have full Pro access to Fal AI Kling 10s video generation."

        self.send_message(chat_id, info, reply_markup=self.main_menu_keyboard())

    def _send_help_info(self, chat_id):
        help_text = (
            "💡 <b>Afrigen Bot Guide</b>\n\n"
            "<b>Commands:</b>\n"
            "• /start - Main menu & connection\n"
            "• /link &lt;code&gt; - Connect your website account\n"
            "• /credits - Check credit balance & plan\n"
            "• /styles - Change visual style\n"
            "• /help - Show this guide\n\n"
            "<b>How to Generate:</b>\n"
            "1. Select <b>Make Video</b> or <b>Make Photo</b>.\n"
            "2. Type your idea, OR hold the mic button to <b>send a voice note</b>.\n"
            "3. Our AI enhances your prompt and delivers your media directly in Telegram!\n\n"
            "<i>Africa Creates, AI Generates 🌍</i>"
        )
        self.send_message(chat_id, help_text, reply_markup=self.main_menu_keyboard())

    def _handle_callback_query(self, query):
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

        if data == "menu_video":
            tg_user.mode = "video"
            db.session.commit()
            self.edit_message_text(
                chat_id, message_id,
                "🎬 <b>Video Mode Active!</b>\n\n"
                f"Active style: <b>{STYLE_NAMES.get(tg_user.style, tg_user.style)}</b>\n\n"
                "Send your prompt or record a voice note to create your video.",
                reply_markup=self.main_menu_keyboard()
            )

        elif data == "menu_image":
            tg_user.mode = "image"
            db.session.commit()
            self.edit_message_text(
                chat_id, message_id,
                "🖼️ <b>Photo Mode Active!</b>\n\n"
                f"Active style: <b>{STYLE_NAMES.get(tg_user.style, tg_user.style)}</b>\n\n"
                "Send your prompt or record a voice note to create your photo.",
                reply_markup=self.main_menu_keyboard()
            )

        elif data == "menu_styles":
            self.edit_message_text(
                chat_id, message_id,
                f"🎨 <b>Choose Your Visual Style:</b>\n\nCurrent: <b>{STYLE_NAMES.get(tg_user.style, tg_user.style)}</b>",
                reply_markup=self.styles_keyboard()
            )

        elif data == "menu_credits":
            self._send_credits_info(tg_user, chat_id)

        elif data == "menu_help":
            self._send_help_info(chat_id)

        elif data == "menu_main":
            self.edit_message_text(
                chat_id, message_id,
                "🌍 <b>Afrigen AI Main Menu</b>\n\nSelect an option below or send your prompt directly:",
                reply_markup=self.main_menu_keyboard()
            )

        elif data.startswith("style_"):
            style_key = data.replace("style_", "")
            tg_user.style = style_key
            db.session.commit()
            style_label = STYLE_NAMES.get(style_key, style_key)
            self.edit_message_text(
                chat_id, message_id,
                f"✅ Style set to: <b>{style_label}</b>\n\n"
                f"Ready in <b>{tg_user.mode.upper()}</b> mode. Send your idea now!",
                reply_markup=self.main_menu_keyboard()
            )

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
                            f"🗣️ <b>Transcribed Prompt:</b>\n<i>\"{prompt_text}\"</i>\n\n🚀 Starting {tg_user.mode} generation..."
                        )

                    self._execute_generation(tg_user.id, chat_id, prompt_text)

                except Exception as exc:
                    logger.exception("Voice note transcription failed: %s", exc)
                    self.send_message(chat_id, f"❌ Voice processing failed: {exc}")
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass

        threading.Thread(target=_voice_worker, daemon=True).start()

    def _handle_text_prompt(self, tg_user, text, chat_id, flask_app):
        app = flask_app or current_app._get_current_object()
        self.send_chat_action(chat_id, "typing")

        def _text_worker():
            with app.app_context():
                self._execute_generation(tg_user.id, chat_id, text)

        threading.Thread(target=_text_worker, daemon=True).start()

    def _execute_generation(self, tg_user_db_id, chat_id, user_prompt):
        tg_user = db.session.get(TelegramUser, tg_user_db_id)
        if not tg_user:
            return

        # 1. Verify User Account Link
        if not tg_user.user:
            self.send_message(
                chat_id,
                "🔗 <b>Connect your Afrigen Account First</b>\n\n"
                "To generate high-quality AI videos & images, link your free account:\n"
                "1. Go to <a href='https://afrigen.com.ng/dashboard'>afrigen.com.ng</a>\n"
                "2. Click <b>Connect Telegram</b> to copy your code\n"
                "3. Send <code>/link &lt;code&gt;</code> here.",
                reply_markup=self.main_menu_keyboard()
            )
            return

        user = tg_user.user
        if user.is_banned:
            self.send_message(chat_id, "❌ Your account is currently restricted.")
            return

        mode = tg_user.mode or "video"
        style = tg_user.style or "cinematic"
        has_free_video = (getattr(user, "free_video_allowance", 0) or 0) > 0
        extended = (user.plan == "pro")

        # 2. Check Credit Gates
        if mode == "image":
            ok, err = image_gate(user)
            cost = 0
            if not ok:
                self.send_message(chat_id, f"❌ {err}\n\n👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade to Pro</a> for more.")
                return
        else:
            ok, err, cost = video_gate(user, style, extended=extended)
            if not ok:
                self.send_message(chat_id, f"❌ {err}\n\n👉 <a href='https://afrigen.com.ng/upgrade'>Upgrade to Pro</a> for unlimited video generation.")
                return

        # 3. Prompt Refinement
        self.send_message(
            chat_id,
            f"🎨 <b>Refining your {mode} idea...</b>\n<i>\"{user_prompt}\"</i>\nStyle: {STYLE_NAMES.get(style, style)}"
        )
        self.send_chat_action(chat_id, "upload_video" if mode == "video" else "upload_photo")

        try:
            if mode == "image":
                refined_prompt = refine_image_prompt(user_prompt, style)
            else:
                refined_prompt = refine_prompt(user_prompt, style)
        except Exception as e:
            logger.warning("Refine error in bot: %s; using original prompt", e)
            refined_prompt = user_prompt

        # 4. Generate Media
        allow_fal = (user.plan == "pro" or has_free_video)
        media_url = None
        error_msg = None

        try:
            if mode == "image":
                provider = "fal" if user.plan == "pro" else "huggingface"
                res = generate_image(refined_prompt, style=style, aspect_ratio="1:1", provider=provider, allow_fal=allow_fal)
                if res and res.get("success"):
                    media_url = res.get("image_url")
                else:
                    error_msg = res.get("error") if res else "Image generation returned no result."
            else:
                wait_note = "this usually takes 1-3 minutes"
                self.send_message(chat_id, f"🎬 <b>Rendering video with AI...</b> ({wait_note})")
                res = generate_video(refined_prompt, style=style, aspect_ratio="16:9", extended=extended, allow_fal=allow_fal)
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
                f"❌ <b>Generation Failed:</b>\n{error_msg or 'Server busy. Please try again shortly.'}",
                reply_markup=self.main_menu_keyboard()
            )
            return

        # 6. Apply On-Screen Text & Free Watermark
        if mode == "video":
            on_screen = extract_on_screen_text(user_prompt)
            if on_screen:
                try:
                    captioned = add_text_overlay(media_url, on_screen)
                    if captioned:
                        media_url = captioned
                except Exception as e:
                    logger.warning("Text overlay error: %s", e)

            # Apply subtle branding watermark for free tier users
            if user.plan != "pro":
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
        caption = (
            f"✨ <b>Made with Afrigen</b>\n\n"
            f"Prompt: <i>\"{user_prompt[:120]}\"</i>\n"
            f"Remaining Credits: {user.credits or 0}\n\n"
            "Africa Creates, AI Generates 🌍"
        )

        try:
            if mode == "image":
                self.send_photo(chat_id, media_url, caption=caption, reply_markup=self.main_menu_keyboard())
            else:
                self.send_video(chat_id, media_url, caption=caption, reply_markup=self.main_menu_keyboard())
        except Exception as e:
            logger.error("Failed to send media to Telegram: %s", e)
            self.send_message(
                chat_id,
                f"✅ <b>Your {mode} is ready!</b>\n\nDownload link:\n{media_url}",
                reply_markup=self.main_menu_keyboard()
            )


telegram_bot = TelegramBotService()

