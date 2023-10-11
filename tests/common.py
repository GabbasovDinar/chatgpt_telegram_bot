from unittest.mock import AsyncMock

import pytest

from bot.database import SessionLocal


@pytest.fixture
def db_session():
    session = SessionLocal()
    transaction = session.begin()
    yield session
    if transaction.is_active:
        transaction.rollback()
    session.close()


@pytest.fixture
def fake_bot():
    return AsyncMock()


@pytest.fixture
def fake_admin_bot():
    return AsyncMock()


@pytest.fixture
def fake_dispatcher(fake_bot):
    fake_dispatcher = AsyncMock()
    fake_dispatcher.bot = fake_bot
    return fake_dispatcher


@pytest.fixture
def fake_admin_dispatcher(fake_admin_bot):
    fake_admin_dispatcher = AsyncMock()
    fake_admin_dispatcher.bot = fake_admin_bot
    return fake_admin_dispatcher
