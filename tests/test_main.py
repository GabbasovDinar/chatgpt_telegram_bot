from unittest.mock import AsyncMock, call, patch

import pytest
from aiogram import types

from bot.bot_responses import responses
from bot.main import handle_start
from bot.models import User

from .common import (  # noqa: F401
    db_session,
    fake_admin_bot,
    fake_admin_dispatcher,
    fake_bot,
    fake_dispatcher,
)

mock_user = AsyncMock(id=123, username="testuser")
mock_chat = AsyncMock(id=123)


@pytest.mark.asyncio
async def test_handle_start(
    db_session,  # noqa: F811
    fake_dispatcher,  # noqa: F811
    fake_bot,  # noqa: F811
    fake_admin_dispatcher,  # noqa: F811
    fake_admin_bot,  # noqa: F811
):
    fake_message = types.Message()
    fake_message.text = "/start"
    fake_message.from_user = mock_user
    fake_message.chat = mock_chat

    with patch("bot.main.dp", fake_dispatcher), patch("bot.main.bot", fake_bot), patch(
        "bot.main.admin_dp", fake_admin_dispatcher
    ), patch("bot.main.admin_bot", fake_admin_bot):
        await handle_start(fake_message, {"db_session": db_session})

    fake_bot.send_message.assert_has_calls(
        [
            call(fake_message.chat.id, responses["handle"]["start"]["new"]),
        ]
    )

    # TODO: fake_admin_bot.send_message.assert_called_once_with

    user = User.get_user_by_telegram_id(db_session, mock_user.id)
    assert user is not None
    assert user.telegram_username == "testuser"

    with patch("bot.main.dp", fake_dispatcher), patch("bot.main.bot", fake_bot), patch(
        "bot.main.admin_dp", fake_admin_dispatcher
    ), patch("bot.main.admin_bot", fake_admin_bot):
        await handle_start(fake_message, {"db_session": db_session})

    fake_bot.send_message.assert_has_calls(
        [
            call(fake_message.chat.id, responses["handle"]["start"]["inactive"]),
        ]
    )

    user.write(db_session, {"state": "banned"})

    with patch("bot.main.dp", fake_dispatcher), patch("bot.main.bot", fake_bot), patch(
        "bot.main.admin_dp", fake_admin_dispatcher
    ), patch("bot.main.admin_bot", fake_admin_bot):
        await handle_start(fake_message, {"db_session": db_session})

    fake_bot.send_message.assert_has_calls(
        [
            call(fake_message.chat.id, responses["handle"]["start"]["banned"]),
        ]
    )
