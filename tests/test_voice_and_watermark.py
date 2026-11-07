import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from telegram import Update, Message, Voice, User, Chat
from telegram.ext import ContextTypes

from services.audio import transcribe_voice_note
from services.video import add_watermark_to_video
from bot.bot import handle_voice


def test_transcribe_voice_note_calls_groq():
    with patch("os.environ.get", return_value="fake_groq_key"), \
         patch("groq.Groq") as mock_groq_class, \
         patch("builtins.open", MagicMock()):
        mock_client = MagicMock()
        mock_groq_class.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "A Nigerian chief at a festival"

        result = transcribe_voice_note("dummy.ogg")
        assert result == "A Nigerian chief at a festival"
        mock_client.audio.transcriptions.create.assert_called_once()


def test_add_watermark_fallback_on_error():
    res = add_watermark_to_video(None)
    assert res is None

    res = add_watermark_to_video("https://invalid.example.com/not_exist.mp4")
    assert res == "https://invalid.example.com/not_exist.mp4"


def test_bot_handle_voice_flow():
    import asyncio

    async def _test():
        update = MagicMock(spec=Update)
        message = AsyncMock(spec=Message)
        voice = MagicMock(spec=Voice)
        voice.file_id = "test_voice_file_id"
        message.voice = voice
        message.audio = None
        message.reply_text = AsyncMock()
        message.chat = AsyncMock(spec=Chat)
        update.message = message
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_chat = AsyncMock(spec=Chat)
        update.effective_chat.id = 67890

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {"style": "cinematic", "mode": "video"}
        tg_file = AsyncMock()
        context.bot.get_file = AsyncMock(return_value=tg_file)

        status_msg = AsyncMock()
        message.reply_text.return_value = status_msg

        with patch("services.audio.transcribe_voice_note", return_value="An African marketplace in the morning"), \
             patch("bot.bot._async_get_gate_status", return_value=(True, None, 0, 1, False, "free", True)):
            await handle_voice(update, context)

            message.reply_text.assert_awaited_once()
            status_msg.edit_text.assert_awaited()
            context.application.create_task.assert_called_once()
            # Clean up spawned coroutine
            task_arg = context.application.create_task.call_args[0][0]
            task_arg.close()

    asyncio.run(_test())
