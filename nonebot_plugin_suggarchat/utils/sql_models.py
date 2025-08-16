from datetime import datetime
from typing import overload

from nonebot_plugin_orm import AsyncSession, Model
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column


class Memory(Model):
    __tablename__ = "suggarchat_memory_data"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ins_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_group: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    messages_json: Mapped[str] = mapped_column(
        Text,
        default="[]",
        nullable=False,
    )
    sessions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("ins_id", "is_group", name="uq_ins_id_is_group"),
        Index("idx_ins_id", "ins_id"),
        Index("idx_is_group", "is_group"),
    )


class GroupConfig(Model):
    __tablename__ = "suggarchat_group_config"
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("suggarchat_memory_data.ins_id"),
        nullable=False,
    )
    enable: Mapped[bool] = mapped_column(Boolean, default=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    fake_people: Mapped[bool] = mapped_column(Boolean, default=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("group_id", name="uq_suggarchat_config_group_id"),
        Index("idx_suggarchat_group_id", "group_id"),
    )


@overload
async def get_or_create_data(
    *, session: AsyncSession, ins_id: int, for_update: bool = False
) -> Memory: ...
@overload
async def get_or_create_data(
    *,
    session: AsyncSession,
    ins_id: int,
    is_group: bool = True,
    for_update: bool = False,
) -> tuple[GroupConfig, Memory]: ...


async def get_or_create_data(
    *,
    session: AsyncSession,
    ins_id: int,
    is_group: bool = False,
    for_update: bool = False,
) -> Memory | tuple[GroupConfig, Memory]:
    async with session:
        stmt = select(Memory).where(
            Memory.ins_id == ins_id, Memory.is_group == is_group
        )
        stmt = stmt.with_for_update() if for_update else stmt
        result = await session.execute(stmt)
        if not (memory := result.scalar()):
            memory = Memory(ins_id=ins_id, is_group=is_group)
            session.add(memory)
            await session.commit()
            await session.refresh(memory)
        if not is_group:
            return memory
        stmt = select(GroupConfig).where(GroupConfig.group_id == ins_id)
        stmt = stmt.with_for_update() if for_update else stmt
        result = await session.execute(stmt)
        if not (group_config := result.scalar()):
            group_config = GroupConfig(group_id=ins_id)
            session.add(group_config)
            await session.commit()
            await session.refresh(group_config)
        return group_config, memory
