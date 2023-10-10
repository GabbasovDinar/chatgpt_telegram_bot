import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import BotCommand
from bot_responses import responses
from config import (
    GPT_MODEL,
    OPENAI_API_KEY,
    SUPERUSER_ID,
    TELEGRAM_ADMIN_BOT_TOKEN,
    TELEGRAM_ADMIN_USER_ID,
    TELEGRAM_MAIN_BOT_TOKEN,
)
from database import engine, session_scope
from models import Base, Message, User
from openai_agent import OpenAIAgent
from sqlalchemy.orm import Session

_logger = logging.getLogger(__name__)

# main bot
bot = Bot(token=TELEGRAM_MAIN_BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# admin bot
admin_bot = Bot(token=TELEGRAM_ADMIN_BOT_TOKEN)
admin_dp = Dispatcher(admin_bot)
admin_dp.middleware.setup(LoggingMiddleware())

# create OpenAI agent
openai_agent = OpenAIAgent(api_key=OPENAI_API_KEY, settings=GPT_MODEL)
# create db tables
Base.metadata.create_all(bind=engine)

# add available bot commands
commands = [
    BotCommand(command="/start", description=responses["commands"]["start"]),
    BotCommand(
        command="/reset_context", description=responses["commands"]["reset_context"]
    ),
    BotCommand(command="/help", description=responses["commands"]["help"]),
]


# check access to bot
class UserActivationMiddleware(BaseMiddleware):
    async def on_pre_process_message(self, message: types.Message, data: dict):
        """
        Check user state and save db session to data
        """
        db_session = session_scope()
        if message.text not in ["/start", "/help"]:
            user = User.get_user_by_telegram_id(db_session, message.from_user.id)
            if not user:
                return await message.answer(responses["access"]["inactive"])
            if user.state != "active":
                return await message.answer(responses["access"][user.state])
        data["db_session"] = db_session

    async def on_post_process_message(
        self, message: types.Message, data: dict, result: any
    ):
        """
        Closing db session after message processing
        """
        db_session = data.pop("db_session", None)
        if db_session:
            db_session.close()


dp.middleware.setup(UserActivationMiddleware())

# TODO:
# @dp.my_chat_member_handler()
# async def bot_chat_member(update: types.ChatMemberUpdated):
#     old_chat_member = update.old_chat_member
#     new_chat_member = update.new_chat_member
#
#     # Проверяем, был ли бот добавлен в чат
#     if old_chat_member.status == "left" and (new_chat_member.status == "member" or new_chat_member.status == "administrator"):
#         chat_id = update.chat.id
#         chat_type = update.chat.type
#         chat_title = update.chat.title
#         chat_username = update.chat.username
#
#         with session_scope() as db_session:
#             # Проверяем, существует ли чат в базе данных
#             chat = get_chat_by_id(db_session, str(chat_id))
#             if not chat:
#                 # Если чата нет в базе данных, создаем новую запись
#                 create_chat(db_session, chat_id=str(chat_id), chat_type=chat_type, chat_title=chat_title, chat_username=chat_username)
#
#         # Отправляем приветственное сообщение в чат
#         await bot.send_message(chat_id, "Привет! Я ваш новый бот. Готов помочь!")
#
# @dp.message_handler(content_types=types.ContentTypes.TEXT)
# async def handle_all_messages(message: types.Message):
#     # Проверка, является ли сообщение из чата
#     if message.chat.type not in ["private"]:
#         # Сохранение сообщения в базе данных
#         with session_scope() as db_session:
#             add_chat_message(db_session, chat_id=message.chat.id, user_id=message.from_user.id, text=message.text)
#
#         # Проверка, обращено ли сообщение к боту (например, упоминание его имени)
#         if bot.username in message.text:
#             # Получение последних 10 сообщений из чата
#             with session_scope() as db_session:
#                 last_messages = get_last_chat_messages(db_session, chat_id=message.chat.id, limit=10)
#
#             # Формирование контекста для OpenAI
#             context = [{"role": "user" if not msg.is_bot else "assistant", "content": msg.text} for msg in
#                        last_messages]
#
#             # Получение ответа от OpenAI
#             response = openai_agent.process_message_with_context(user_id=message.from_user.id, message=message.text,
#                                                                  context=context)
#
#             # Отправка ответа в чат
#             await bot.send_message(message.chat.id, response)

# ===========================================
# ========== Handlers for Main Bot ==========
# ===========================================


@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message, data: dict):
    db_session = data["db_session"]
    await bot.set_my_commands(commands)
    try:
        user = User.get_user_by_telegram_id(db_session, message.from_user.id)
        if user:
            response = responses["handle"]["start"][user.state]
        else:
            response = responses["handle"]["start"]["new"]
            values = {
                "telegram_id": message.from_user.id,
                "telegram_username": message.from_user.username,
            }
            user = User.create(db_session, values)
            await admin_bot.send_message(
                TELEGRAM_ADMIN_USER_ID,
                f"New user registration request: {user.telegram_username}. "
                f"Use /approve {user.telegram_id} to approve.",
            )
        # send response from bot to user
        await bot.send_message(
            message.chat.id,
            response,
        )
    except Exception as e:
        _logger.error(f"Error handling /start command: {e}")
        await bot.send_message(message.chat.id, responses["unknown_error"])


@dp.message_handler(commands=["help"])
async def handle_help(message: types.Message):
    await bot.send_message(message.chat.id, responses["handle"]["help"])


@dp.message_handler(commands=["reset_context"])
async def reset_context_command(message: types.Message):
    await reset_context(message)


def is_reset_context_command(message: types.Message) -> bool:
    return message.text == "/reset_context"


@dp.message_handler(is_reset_context_command)
async def reset_context(message: types.Message):
    markup = types.InlineKeyboardMarkup()
    item_yes = types.InlineKeyboardButton(
        responses["handle"]["reset_context"]["confirmation"]["confirm"]["button"],
        callback_data="reset_yes",
    )
    item_no = types.InlineKeyboardButton(
        responses["handle"]["reset_context"]["confirmation"]["cancel"]["button"],
        callback_data="reset_no",
    )
    markup.add(item_yes, item_no)
    await bot.send_message(
        message.chat.id,
        responses["handle"]["reset_context"]["confirmation"]["message"],
        reply_markup=markup,
    )


@dp.callback_query_handler(lambda c: c.data == "reset_yes")
async def process_callback_reset_yes(
    callback_query: types.CallbackQuery, db_session: Session
):
    user = User.get_user_by_telegram_id(db_session, message.from_user.id)
    user.reset_context(db_session)
    await bot.answer_callback_query(
        callback_query.id,
        responses["handle"]["reset_context"]["confirmation"]["confirm"]["answer"],
    )
    await bot.send_message(
        callback_query.from_user.id,
        responses["handle"]["reset_context"]["confirmation"]["confirm"]["callback"],
    )


@dp.callback_query_handler(lambda c: c.data == "reset_no")
async def process_callback_reset_no(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(
        callback_query.id,
        responses["handle"]["reset_context"]["confirmation"]["cancel"]["answer"],
    )
    await bot.send_message(
        callback_query.from_user.id,
        responses["handle"]["reset_context"]["confirmation"]["cancel"]["callback"],
    )


# handler for text messages
@dp.message_handler(lambda message: not message.text.startswith("/"))
async def handle_text_message(message: types.Message, data: dict):
    db_session = data["db_session"]
    user = User.get_user_by_telegram_id(db_session, message.from_user.id)
    Message.post(db_session, author=user, text=message.text)
    # bot typing
    await bot.send_chat_action(message.chat.id, types.ChatActions.TYPING)
    # get group context with last message
    group = user.get_private_group(db_session)
    # prepare context message for ChatGPT
    context = group.get_format_context(db_session)
    # send message to ChatGPT
    response = openai_agent.process_message(context)
    # save bot message to database
    Message.post(db_session, text=response, group=group)
    # send response to user
    await bot.send_message(message.from_user.id, response)


# TODO
# ============================================
# ========== Handlers for Admin Bot ==========
# ============================================


class AdminAccessMiddleware(BaseMiddleware):
    async def on_pre_process_message(self, message: types.Message, data: dict):
        if str(message.from_user.id) != TELEGRAM_ADMIN_USER_ID:
            await message.answer(responses["access"]["error"])
            # TODO: CancelHandler()
            raise CancelHandler()
        db_session = session_scope()
        data["db_session"] = db_session

    async def on_post_process_message(
        self, message: types.Message, data: dict, result: any
    ):
        """
        Closing db session after message processing
        """
        db_session = data.pop("db_session", None)
        if db_session:
            db_session.close()


admin_dp.middleware.setup(AdminAccessMiddleware())


@admin_dp.message_handler(commands=["sendto"])
async def handle_sendto(message: types.Message, db_session: Session):
    parts = message.text.split(" ", 2)
    if len(parts) <= 2:
        return await message.reply(
            "Пожалуйста, укажите ID или ник пользователя и сообщение для отправки."
        )

    user_identifier, user_message = parts[1], parts[2]
    if user_identifier.isdigit():
        user = User.get_user_by_telegram_id(db_session, user_identifier)
    else:
        user = User.get_user_by_telegram_username(db_session, user_identifier)

    if not user:
        return await message.reply(
            f"Пользователь с ID или ником '{user_identifier}' не найден."
        )
    await bot.send_message(user.telegram_id, user_message)
    await message.reply(f"Сообщение отправлено пользователю {user_identifier}.")


@admin_dp.message_handler(commands=["broadcast"])
async def handle_broadcast(message: types.Message, db_session: Session):
    """
    Send message to all active users
    """
    broadcast_message = message.text.split(" ", 1)
    if len(broadcast_message) <= 1:
        return await message.reply(
            "Пожалуйста, укажите сообщение для рассылки после команды."
        )

    broadcast_message = broadcast_message[1]
    domain = [("state", "=", "active"), ("role", "!=", "bot")]
    users = User.search(db, domain)
    for user in users:
        group = user.get_private_group(db_session)
        Message.post(db_session, text=response, group=group)
        await bot.send_message(user.telegram_id, broadcast_message)
    await message.reply(f"Сообщение отправлено {len(users)} пользователям.")


@admin_dp.message_handler(commands=["sendtochat"])
async def handle_sendtochat(message: types.Message):

    parts = message.text.split(" ", 2)
    if len(parts) <= 2:
        await message.reply(
            "Пожалуйста, укажите ID чата или канала и сообщение для отправки."
        )
        return

    chat_id, chat_message = parts[1], parts[2]

    # TODO: check from group table
    try:
        await bot.send_message(chat_id, chat_message)
        await message.reply(f"Сообщение успешно отправлено в чат/канал с ID {chat_id}.")
    except Exception as e:
        await message.reply(f"Ошибка при отправке сообщения в чат/канал: {e}")


# TODO: refactoring block and unblock command use /approve and /reject
@admin_dp.message_handler(lambda message: message.text.startswith("/approve"))
async def handle_approve(message: types.Message, db_session: Session):
    user_id = message.text.split()[1]
    # TODO: or by telegram username
    user = User.get_user_by_telegram_id(db_session, user_id)
    if user:
        user.write({"state": "active"})
        await message.reply(f"Пользователь {user_id} был активирован.")
        # TODO: text
        await bot.send_message(
            user.telegram_id, "Поздравляю, Ваш аккаунт был активирован!"
        )
    else:
        await message.reply(f"Пользователь {user.telegram_id} не найден.")


@admin_dp.message_handler(lambda message: message.text.startswith("/reject"))
async def handle_reject(message: types.Message, db_session: Session):
    user_id = message.text.split()[1]
    user = User.get_user_by_telegram_id(db_session, user_id)
    if user:
        user.write({"state": "banned"})
        await message.reply(f"Пользователь {user.telegram_id} был заблокирован.")
        # TODO: text
        await bot.send_message(user.telegram_id, "Ваш аккаунт был заблокирован.")
    else:
        await message.reply(f"Пользователь {user.telegram_id} не найден.")


@admin_dp.message_handler(lambda message: message.text.startswith("/"))
async def handle_unknown_command(message: types.Message):
    await message.reply(responses.get("unknown_command"))


# ==========================
# ========== Main ==========
# ==========================


def init_db():
    with session_scope() as db_session:
        bot = User.get_user_by_telegram_id(db_session, SUPERUSER_ID)
        if not bot:
            # TODO, create bot with migration
            values = {
                "telegram_id": SUPERUSER_ID,
                "telegram_username": "Bot",
                "role": "bot",
            }
            bot = User.create(db_session, values)
            bot.state = "active"


async def start_bot():
    try:
        await dp.start_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await dp.storage.close()
        await dp.storage.wait_closed()


async def start_admin_bot():
    try:
        await admin_dp.start_polling()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await admin_dp.storage.close()
        await admin_dp.storage.wait_closed()


async def main():
    await asyncio.gather(start_bot(), start_admin_bot())


if __name__ == "__main__":
    init_db()
    asyncio.run(main())
