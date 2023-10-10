from bot.models import Group, Message, User

from .common import db_session  # noqa: F401


def create_user(db_session):  # noqa: F811
    user_data = {
        "telegram_id": 123456,
        "telegram_username": "testuser",
        "state": "active",
        "role": "user",
    }
    user = User.create(db_session, user_data)
    return user


def test_create_user(db_session):  # noqa: F811
    user = create_user(db_session)
    assert user is not None
    assert user.telegram_id == 123456


def test_get_user_by_telegram_id(db_session):  # noqa: F811
    user = create_user(db_session)
    user = User.get_user_by_telegram_id(db_session, user.telegram_id)
    assert user is not None
    assert user.telegram_username == "testuser"


def test_update_user(db_session):  # noqa: F811
    user = create_user(db_session)
    updated_data = {"telegram_username": "updateduser"}
    user.write(db_session, updated_data)
    updated_user = User.get_user_by_telegram_id(db_session, user.telegram_id)
    assert updated_user.telegram_username == "updateduser"


def test_delete_user(db_session):  # noqa: F811
    user = create_user(db_session)
    user.delete(db_session)
    deleted_user = User.get_user_by_telegram_id(db_session, user.telegram_id)
    assert deleted_user is None


def test_user_group_relationship(db_session):  # noqa: F811
    user = create_user(db_session)
    group = Group.create(db_session, {"title": "Test Group"})
    user.write(db_session, {"groups": group})
    assert group in user.groups


def test_reset_context(db_session):  # noqa: F811
    user = create_user(db_session)
    group = Group.create(db_session, {"title": "Test Group"})
    assert len(group.context_messages) == 0
    Message.post(db_session, text="Test Message", author=user, group=group)
    assert len(group.context_messages) == 1
    group.reset_context(db_session)
    assert len(group.context_messages) == 0
