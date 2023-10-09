import logging
from typing import Any, List, Type, TypeVar

from config import SUPERUSER_ID
from models import Base, Group, Message, User, UserGroupRel
from sqlalchemy.orm import Session
from sqlalchemy.orm.collections import InstrumentedList

_logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Base)

################################################
##################### Main #####################
################################################


def delete_from_db(db: Session, item: T) -> T:
    """
    Common method to delete record from DB:
    """
    try:
        db.delete(item)
        db.flush()
        return True
    except Exception as e:
        db.rollback()
        _logger.error(f"An error occurred: {e}")


def add_to_db(db: Session, item: T) -> T:
    """
    Common method to add new record to DB
    """
    try:
        db.add(item)
        db.flush()
        return item
    except Exception as e:
        db.rollback()
        _logger.error(f"An error occurred: {e}")


def update_db(db: Session, item: T, values: dict) -> T:
    """
    Common method to update records in DB
    """
    try:
        for key, value in values.items():
            attr = getattr(item, key)
            if isinstance(attr, InstrumentedList):
                # If the attribute is a relationship field, append the new value
                attr.append(value)
            else:
                # Otherwise, set the new value
                setattr(item, key, value)
        db.flush()
        return item
    except Exception as e:
        db.rollback()
        _logger.error(f"An error occurred: {e}")


def get_by_field(db: Session, model: Type[T], field: str, value: Any) -> T:
    """
    Common method to get record from db
    """
    return db.query(model).filter(getattr(model, field) == value).one_or_none()


################################################
##################### User #####################
################################################


def create_user(
    db: Session, telegram_id: int, telegram_username: str, **kwargs
) -> User:
    """
    Create new user with new private group with a bot
    """
    user = add_to_db(
        db, User(telegram_id=telegram_id, telegram_username=telegram_username, **kwargs)
    )
    # create private group with bot
    private_group = create_group(
        db, type="private", title=f"Private group for {user.telegram_username}"
    )
    # add new user to new private group
    add_to_db(db, UserGroupRel(user_id=user.id, group_id=private_group.id))
    # find bot
    bot = get_user_by_telegram_id(db, SUPERUSER_ID)
    # add the bot to private group with new user
    add_to_db(db, UserGroupRel(user_id=bot.id, group_id=private_group.id))
    return user


def get_user_by_id(db: Session, user_id: int) -> User:
    """
    Return user found by user ID
    """
    return get_by_field(db, User, "id", user_id)


def get_user_by_telegram_id(db: Session, telegram_id: int) -> User:
    """
    Return user found by telegram ID
    """
    return get_by_field(db, User, "telegram_id", telegram_id)


def get_user_by_telegram_username(db: Session, telegram_username: str) -> User:
    """
    Return user found by telegram username
    """
    return get_by_field(db, User, "telegram_username", telegram_username)


def get_inactive_users(db: Session):
    """
    Get inactive users to approve or reject his requests
    """
    return db.query(User).filter(User.state == "inactive").all()


def get_active_users(db: Session):
    """
    Get all active (approved) users
    """
    return (
        db.query(User)
        .filter((User.state == "active") & (User.id != SUPERUSER_ID))
        .all()
    )


def get_banned_users(db: Session):
    """
    Get all banned (rejected) users
    """
    return db.query(User).filter(User.state == "banned").all()


def get_user_messages(db: Session, telegram_id: int, limit: int = 20):
    """
    Return last N user messages
    """
    return (
        db.query(Message)
        .join(User, User.id == Message.user_id)
        .filter(User.telegram_id == telegram_id)
        .order_by(desc(Message.datetime))
        .limit(limit)
        .all()
    )


def delete_user(db: Session, telegram_id: int):
    """
    Delete user by telegram ID
    """
    user = get_user_by_telegram_id(db, telegram_id)
    if not user:
        return False
    return delete_from_db(db, user)


def get_user_private_group(db: Session, user_id: int):
    """
    Return user private group
    """
    user = get_user_by_id(db, user_id)
    for group in user.groups:
        if group.type == "private":
            return group
    return None


def get_users_by_role(db: Session, role: str):
    """
    Return users by role
    """
    return db.query(User).filter(User.role == role).all()


def get_bot(db: Session):
    """
    Return bot
    """
    bot_users = get_users_by_role(db, "bot")
    bot_users[0] if bot_users else None

    return bot_users[0] if bot_users else None


################################################
#################### Message ###################
################################################


def get_message_by_id(db: Session, message_id: int) -> Message:
    """
    Return message by id
    """
    return get_by_field(db, Message, "id", message_id)


def add_message(db: Session, user_id: int, text: str, **kwargs) -> Message:
    """
    Add new message to group and save is to group context
    """
    # TODO: add arguments: 'from_user', 'to_group'
    # TODO: add checks and exceptions for each method
    group_id = kwargs.get("group_id") or get_user_private_group(db, user_id).id
    message = add_to_db(
        db, Message(user_id=user_id, group_id=group_id, text=text, **kwargs)
    )
    group = get_group_by_id(db, group_id)
    update_db(db, group, {"context_messages": message})
    return message


def delete_message(db: Session, message_id: int) -> None:
    """
    Delete message by message ID
    """
    message = get_message_by_id(db, message_id)
    if not message:
        return False
    return delete_from_db(db, message)


################################################
##################### Group ####################
################################################


def create_group(db: Session, **kwargs) -> Group:
    """
    Create new group
    """
    return add_to_db(db, Group(**kwargs))


def get_group_by_telegram_id(db: Session, telegram_id: str) -> Group:
    """
    Return Group found by telegram ID
    """
    return get_by_field(db, Group, "telegram_id", telegram_id)


def get_group_by_id(db: Session, group_id: int) -> Group:
    """
    Return group found by group ID
    """
    return get_by_field(db, Group, "id", group_id)


def get_all_groups(db: Session):
    """
    Return all groups
    """
    return db.query(Group).all()


def get_last_group_messages(
    db: Session, group_id: str, limit: int = 20
) -> List[Message]:
    """
    Return last N message for group
    """
    return (
        db.query(Message)
        .filter(Message.group_id == group_id)
        .order_by(Message.datetime.desc())
        .limit(limit)
        .all()
    )


################################################
################### Context ####################
################################################


def reset_context(db: Session, group_id: int):
    """
    Reset group context
    """
    try:
        group = get_group_by_id(db, group_id)
        for message in group.context_messages:
            update_db(db, message, {"context_group": None})
    except Exception as e:
        _logger.error(f"An error occurred: {e}")


def get_format_context(db: Session, group_id: int):
    """
    Return list of messages formatted for OpenAI
    """
    group = get_group_by_id(db, group_id)
    conversation = [
        {
            "role": "system",
            "content": "The assistant is helpful, creative, smart and very friendly.",
        }
    ]
    # TODO: order_by
    for message in group.context_messages:
        conversation.append(
            {
                "role": "user" if message.user.id != SUPERUSER_ID else "assistant",
                "content": message.text,
            }
        )
    return conversation
