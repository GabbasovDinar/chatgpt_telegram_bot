import logging
import re
from typing import List, Optional, Tuple, TypeVar

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
from sqlalchemy.orm import InstrumentedList, Session, relationship
from sqlalchemy.sql import func

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
            return None

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
            return None

    def parse_domain(self, domain: List, query):
        """
        Recursive function to parse domain in prefix notation
        """
        if not domain:
            return []

        op = domain.pop(0)
        if op in LOGICAL_OPS:
            if op == "!":
                condition = self.parse_domain(domain, query)
                return LOGICAL_OPS[op](condition)
            else:
                left_condition = self.parse_domain(domain, query)
                right_condition = self.parse_domain(domain, query)
                return LOGICAL_OPS[op](left_condition, right_condition)
        else:
            field, operation, value = op
            return OPERATIONS[operation](getattr(self, field), value)

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


T = TypeVar("T", bound=BaseModel)


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
            db, {name: f"Private Group for {new_user.telegram_username}"}
        )
        new_user.groups.append(new_group)
        bot = ""
        bot.groups.append(new_group)
        db.flush()
        return new_user


class Message(BaseModel):
    __tablename__ = "messages"

    text = Column(String, index=True)
    datetime = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"))
    group_id = Column(Integer, ForeignKey("groups.id"))

    user = relationship("User", back_populates="messages")
    context_group = relationship("Group", back_populates="context_messages")
    group = relationship("Group", back_populates="messages")


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


user_group_rels = Table(
    "user_group_rels",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("group_id", Integer, ForeignKey("groups.id")),
)
