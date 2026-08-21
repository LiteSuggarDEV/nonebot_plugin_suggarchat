from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Literal, cast

from aiologic import Lock
from nonebot.adapters.onebot.v11 import Event
from nonebot_plugin_amrita.database import (
    HasUserIDModel,
    Memory,
    SqlModel_T,
    UserMetadata,
)
from nonebot_plugin_orm import AsyncSession, Model, get_session
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSessionTransaction
from sqlalchemy.orm import Mapped, mapped_column
from typing_extensions import Self

from .lock import database_lock


def get_uni_user_id(event: Event) -> str:
    if uid := getattr(event, "group_id", None):
        return f"group_{uid!s}"
    else:
        return f"user_{event.get_user_id()!s}"


async def get_user_metadata_or_none(uni_user_id: str) -> UserMetadata | None:
    """只读查询指定 uni_user_id 的元数据，不存在时返回 None（不会创建记录）"""
    async with get_session() as session:
        stmt = select(UserMetadata).where(UserMetadata.user_id == uni_user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


def get_any_id(event: Event) -> tuple[int, bool]:
    if uid := getattr(event, "group_id", None):
        return uid, True
    else:
        return int(event.get_user_id()), False


def make_uni_id(id: int, is_group: bool) -> str:
    return f"{'group' if is_group else 'user'}_{id!s}"


VALIDATE_PATTERN = re.compile(r"^(user|group)_[0-9]+$")
UNWRAP_PATTERN = re.compile(r"^(user|group)_[0-9]+$")


def validate_uni_user_id(user_id: str) -> bool:
    return bool(VALIDATE_PATTERN.match(user_id))


def validate_and_ret(uid: str) -> str:
    if validate_uni_user_id(uid):
        return uid
    raise ValueError(f"Invalid uni_user_id: {uid}")


def unwrap_uni_user_id(user_id: str) -> tuple[Literal["user", "group"], int]:
    match = UNWRAP_PATTERN.match(user_id)
    if not match:
        raise ValueError(f"Invalid uni_user_id: {user_id}")
    if TYPE_CHECKING:
        return cast(Literal["user", "group"], match.group(1)), int(match.group(2))
    else:
        return match.group(1), int(match.group(2))


class GroupConfig(Model, HasUserIDModel):
    __tablename__ = "amrita_group_config"
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{UserMetadata.__tablename__}.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    enable: Mapped[bool] = mapped_column(Boolean, default=True)
    autoreply: Mapped[bool] = mapped_column(Boolean, default=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_amrita_group_config_user_id"),
        Index("idx_amrita_group_config_user_id", "user_id"),
    )


class GroupConfigExecutor:
    session: AsyncSession
    group_id: str
    _lock: Lock
    _transaction: AsyncSessionTransaction  # (lateinit) When __aenter__ is called, this will be set
    _arg_session: AsyncSession | None = None
    _group_config_temp: GroupConfig | None = (
        None  # (lazy) This will be set when group config is accessed, and can be used to batch updates
    )
    _user_memory_temp: Memory | None = None
    _entered: bool = False  # Mark whether the context manager has been entered, to prevent multiple __aenter__ calls
    __for_update: bool = False

    def __init__(
        self,
        group_id: str,
        session: AsyncSession | None = None,
        /,
        with_for_update: bool = False,
    ):
        if not validate_uni_user_id(group_id):
            raise ValueError(f"Invalid uni_user_id format: {group_id}")
        self.group_id = group_id
        self._arg_session = session
        self.session = session or get_session()
        self._lock = database_lock(group_id)
        self.__for_update = with_for_update

    async def __aenter__(self) -> Self:
        self._entered = True
        await self._lock.__aenter__()
        self._transaction = self.session.begin()
        if self._arg_session is None:
            await self.session.__aenter__()
        await self._transaction.__aenter__()
        # Ensure UserMetadata row exists to satisfy FK constraint
        stmt = select(UserMetadata.id).where(UserMetadata.user_id == self.group_id)
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none() is None:
            self.session.add(UserMetadata(user_id=self.group_id))
            await self.session.flush()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if exc_type is not None:
                await self._transaction.rollback()
            else:
                await self._transaction.commit()
            await self._transaction.__aexit__(exc_type, exc_value, traceback)
            if self._arg_session is None:
                await self.session.__aexit__(exc_type, exc_value, traceback)
        finally:
            self._entered = False
            await self._lock.__aexit__(exc_type, exc_value, traceback)

    async def _get_or_create_any(self, model: type[SqlModel_T], **kwargs) -> SqlModel_T:
        stmt = select(model).where(model.user_id == self.group_id)
        stmt = stmt if not self.__for_update else stmt.with_for_update()
        result = await self.session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            obj = model(user_id=self.group_id, **kwargs)
            self.session.add(obj)
            await (
                self.session.flush()
            )  # Ensure the new object is persisted before returning
        else:
            self.session.add(obj)
        return obj

    async def get_or_create_group_config(self) -> GroupConfig:
        if not self.group_id.startswith("group_"):
            raise ValueError("Group config can only be accessed for group users")
        if self._group_config_temp is not None:
            return self._group_config_temp
        data: GroupConfig = await self._get_or_create_any(GroupConfig)
        self._group_config_temp = data
        return data

    async def get_or_create_memory(self) -> Memory:
        if self._user_memory_temp is not None:
            return self._user_memory_temp
        data: Memory = await self._get_or_create_any(Memory, memory_json={})
        self._user_memory_temp = data
        return data
