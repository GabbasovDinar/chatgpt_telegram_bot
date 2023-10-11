import logging
import re
from typing import Any, List, Optional, Tuple, TypeVar

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    and_,
    not_,
    or_,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.sql import func

# TODO: from env
BOT_TELEGRAM_ID = 1

_logger = logging.getLogger(__name__)

Base = declarative_base()

OPERATIONS = {
    "=": lambda f, v: f == v,
    "!=": lambda f, v: f != v,
    ">": lambda f, v: f > v,
    "<": lambda f, v: f < v,
    ">=": lambda f, v: f >= v,
    "<=": lambda f, v: f <= v,
    "like": lambda f, v: f.like(v),
    "ilike": lambda f, v: f.ilike(v),
    "in": lambda f, v: f.in_(v),
}

LOGICAL_OPS = {"|": or_, "&": and_, "!": not_}

ORDER_PATTERN = re.compile(r"(\w+)\s+(asc|desc)", re.I)

T = TypeVar("T", bound="BaseModel")


class BaseModel(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    create_datetime = Column(DateTime(timezone=True), server_default=func.now())
    write_datetime = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<{self.__tablename__}(id={self.id})>"

    def delete(self: T, db: Session):
        """
        Common method to delete record from DB:
        """
        try:
            db.delete(self)
            db.flush()
            return True
        except Exception as e:
            db.rollback()
            _logger.error(f"An error occurred: {e}")

    @classmethod
    def create(cls, db: Session, values: dict) -> T:
        """
        Common class method to add a new record to DB with given values
        """
        instance = cls(**values)
        try:
            db.add(instance)
            db.flush()
            return instance
        except Exception as e:
            db.rollback()
            _logger.error(f"An error occurred: {e}")
            raise e

    def write(self: T, db: Session, values: dict) -> T:
        """
        Common method to update records in DB
        """
        try:
            for key, value in values.items():
                attr = getattr(self, key)
                if isinstance(attr, InstrumentedList):
                    # If the attribute is a relationship field, append the new value
                    attr.append(value)
                else:
                    # Otherwise, set the new value
                    setattr(self, key, value)
            db.flush()
            return self
        except Exception as e:
            db.rollback()
            _logger.error(f"An error occurred: {e}")
            raise e

    @classmethod
    def parse_domain(cls, domain: List, query):
        """
        Recursive function to parse domain in prefix notation
        """
        if not domain:
            return []

        op = domain.pop(0)
        if op in LOGICAL_OPS:
            if op == "!":
                condition = cls.parse_domain(domain, query)
                return LOGICAL_OPS[op](condition)
            else:
                left_condition = cls.parse_domain(domain, query)
                right_condition = cls.parse_domain(domain, query)
                return LOGICAL_OPS[op](left_condition, right_condition)
        else:
            field, operation, value = op
            return OPERATIONS[operation](getattr(cls, field), value)

    @classmethod
    def search(
        cls,
        db: Session,
        domain: List[Tuple[str, str, Any]],
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> List["BaseModel"]:
        """
        Common method to get records from db
        """
        query = db.query(cls)
        condition = cls.parse_domain(domain, query)
        query = query.filter(condition)

        if limit:
            query = query.limit(limit)

        if order:
            order_clauses = [
                getattr(self, field).asc()
                if direction.lower() == "asc"
                else getattr(self, field).desc()
                for field, direction in ORDER_PATTERN.findall(order)
            ]
            query = query.order_by(*order_clauses)

        return query.all()


user_group_rels = Table(
    "user_group_rels",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("group_id", Integer, ForeignKey("groups.id")),
)


class User(BaseModel):
    __tablename__ = "users"

    telegram_id = Column(Integer, nullable=False, unique=True, index=True)
    telegram_username = Column(String, nullable=True, index=True)
    state = Column(
        Enum("inactive", "active", "banned", name="state"),
        nullable=False,
        default="inactive",
    )
    role = Column(
        Enum("bot", "user", "admin", name="role"), nullable=False, default="user"
    )

    messages = relationship("Message", back_populates="user")
    groups = relationship("Group", secondary=user_group_rels, back_populates="users")

    @classmethod
    def create(cls, db: Session, values: dict) -> T:
        new_user = super().create(db, values)
        new_group = Group.create(
            db, {"title": f"Private Group for {new_user.telegram_username}"}
        )
        new_user.write(db, {"groups": new_group})
        bot = cls.get_bot(db)
        bot.write(db, {"groups": new_group})
        db.flush()
        return new_user

    @classmethod
    def get_user_by_telegram_id(cls, db: Session, telegram_id) -> T:
        domain = [("telegram_id", "=", telegram_id)]
        user = User.search(db, domain, limit=1)
        return user[0] if user else None

    @classmethod
    def get_user_by_telegram_username(cls, db: Session, telegram_username) -> T:
        domain = [("telegram_username", "=", telegram_username)]
        user = User.search(db, domain, limit=1)
        return user

    def get_private_group(self, db: Session):
        """
        Get the private group associated with the user.
        """
        group = filter(lambda group: group.type == "private", self.groups)
        return group[0]

    @classmethod
    def get_bot(cls, db: Session):
        """
        Return ChatGPT Bot
        """
        return User.get_user_by_telegram_id(db, BOT_TELEGRAM_ID)

    def reset_context(self, db: Session):
        """
        Reset private group context
        """
        group = user.get_private_group(db)
        group.reset_context(db)
        return True

    @classmethod
    def get_active_users(cls, db: Session):
        domain = [("state", "=", "active"), ("role", "!=", "bot")]
        users = User.search(db, domain)
        return users


class Message(BaseModel):
    __tablename__ = "messages"

    text = Column(String, index=True)
    datetime = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"))
    group_id = Column(Integer, ForeignKey("groups.id"))

    user = relationship("User", back_populates="messages")
    context_group = relationship("Group", back_populates="context_messages")
    group = relationship("Group", back_populates="messages")

    @classmethod
    def post(
        cls, db: Session, text: str, author: "User" = None, group: "Group" = None
    ) -> "Message":
        """
        Create message record and update group context
        """
        group = group or author.get_private_group(db)
        user = author or User.get_bot(db)
        message = Message.create(
            db,
            {
                "text": text,
                "user_id": user.id,
                "group_id": group.id,
            },
        )
        group.write(
            db,
            {
                "context_messages": message,
            },
        )
        return message


class Group(BaseModel):
    __tablename__ = "groups"

    telegram_id = Column(String(255), nullable=True)
    type = Column(
        Enum("private", "group", "supergroup", "channel", name="type"),
        default="private",
    )
    title = Column(String, nullable=True)
    telegram_username = Column(String, nullable=True)

    messages = relationship("Message", back_populates="group")
    context_messages = relationship("Message", back_populates="context_group")
    users = relationship("User", secondary=user_group_rels, back_populates="groups")

    def reset_context(self, db: Session):
        """
        Reset group context
        """
        for message in self.context_messages:
            message.write(db, {"context_group": None})

    def get_format_context(self, db: Session):
        """
        Return list of messages formatted for OpenAI
        """
        # TODO: get AI role settings from ENV
        conversation = [
            {
                "role": "system",
                "content": "The assistant is helpful, creative, smart and very friendly.",
            }
        ]
        conversation.extend(
            [
                {
                    "role": "assistant" if message.user.role == "bot" else "user",
                    "content": message.text,
                }
                for message in self.context_messages
            ]
        )
        return conversation
