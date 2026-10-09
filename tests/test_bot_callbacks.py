import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, CallbackQuery, User, Message, Chat
from telegram.ext import ContextTypes
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.bot import handle_style_selection

@pytest.mark.asyncio
async def test_handle_style_selection():
    # Test every single callback_data to ensure they don't crash
    callbacks = [
        "menu_video", "menu_image", "menu_styles", "menu_help",
        "style_cinematic", "style_anime", "style_realistic", "style_african", "style_social"
    ]
    
    for cb_data in callbacks:
        update = MagicMock(spec=Update)
        query = AsyncMock(spec=CallbackQuery)
        query.data = cb_data
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 123456789
        
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        
        try:
            await handle_style_selection(update, context)
        except Exception as e:
            pytest.fail(f"Handler raised an exception for callback '{cb_data}': {e}")
            
        # Ensure answer was awaited
        query.answer.assert_awaited_once()
        # Ensure edit_message_text was called
        assert query.edit_message_text.await_count > 0

    print("All callback handlers passed successfully.")
