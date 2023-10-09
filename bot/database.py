import logging
from contextlib import contextmanager

from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

_logger = logging.getLogger(__name__)

# Creating a database engine
engine = create_engine(DATABASE_URL)

# Creating a session factory
SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
)

# Defining a base class for models
Base = declarative_base()


@contextmanager
def session_scope():
    """
    Provide a transactional scope around a series of operations.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        _logger.error(f"An error occurred: {e}")
        raise
    finally:
        session.close()
