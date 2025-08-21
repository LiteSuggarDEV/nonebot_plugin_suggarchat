import json
import time
from datetime import datetime, timedelta
from typing import Any, Literal, overload

from nonebot_plugin_orm import AsyncSession, Model, get_session
from pydantic import BaseModel as B_Model
from pydantic import Field
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column
from typing_extensions import Self

from ..config import config_manager
from .lock import database_lock

# Pydantic 模型


class BaseModel(B_Model):
    def __str__(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=True)

    def __repr__(self) -> str:
        return self.__str__()

    def __getitem__(self, key: str) -> Any:
        return self.model_dump()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.__setattr__(key, value)


class ImageUrl(BaseModel):
    url: str = Field(..., description="图片URL")


class ImageContent(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl = Field(..., description="图片URL")


class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str = Field(..., description="文本内容")


class Message(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(..., description="角色")
    content: str | list[TextContent | ImageContent] = Field(..., description="内容")


class ToolResult(BaseModel):
    role: Literal["tool"] = Field(default="tool", description="角色")
    name: str = Field(..., description="工具名称")
    content: str = Field(..., description="工具返回内容")
    tool_call_id: str = Field(..., description="工具调用ID")


class MemoryModel(BaseModel):
    messages: list[Message | ToolResult] = Field(default_factory=list)
    time: float = Field(default_factory=time.time, description="时间戳")


class InsightsModel(BaseModel):
    date: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d"), description="日期"
    )
    token_input: int = Field(..., description="输入token使用量")
    token_output: int = Field(..., description="输出token使用量")
    usage_count: int = Field(..., description="聊天请求次数")

    @classmethod
    async def get(cls) -> Self:
        date_now = datetime.now().strftime("%Y-%m-%d")
        async with database_lock(date_now):
            async with get_session() as session:
                await cls._delete_expired(
                    days=config_manager.config.usage_limit.global_insights_expire_days,
                    session=session,
                )
                if (
                    insights := (
                        await session.execute(
                            select(GlobalInsights).where(
                                GlobalInsights.date == date_now
                            )
                        )
                    ).scalar_one_or_none()
                ) is None:
                    stmt = insert(GlobalInsights).values(date=date_now)
                    await session.execute(stmt)
                    insights = (
                        await session.execute(
                            select(GlobalInsights).where(
                                GlobalInsights.date == date_now
                            )
                        )
                    ).scalar_one()
                session.add(insights)
                instance = cls.model_validate(insights, from_attributes=True)
            return instance

    async def save(self):
        """保存数据"""
        async with database_lock(self.date):
            async with get_session() as session:
                await self._delete_expired(
                    days=config_manager.config.usage_limit.global_insights_expire_days,
                    session=session,
                )
                stmt = select(GlobalInsights).where(GlobalInsights.date == self.date)
                if ((await session.execute(stmt)).scalar_one_or_none()) is None:
                    stmt = insert(GlobalInsights).values(
                        **{
                            k: v
                            for k, v in self.model_dump().items()
                            if hasattr(GlobalInsights, k)
                        }
                    )
                    await session.execute(stmt)
                    await session.commit()
                else:
                    stmt = (
                        update(GlobalInsights)
                        .where(GlobalInsights.date == self.date)
                        .values(
                            **{
                                k: v
                                for k, v in self.model_dump().items()
                                if hasattr(GlobalInsights, k)
                            }
                        )
                    )
                    await session.execute(stmt)
                    await session.commit()

    @staticmethod
    async def _delete_expired(*, days: int, session: AsyncSession) -> int:
        """
        删除过期的记录

        Args:
            days: 保留天数，超过此天数的记录将被删除
        """
        # 计算截止日期
        cutoff_date = datetime.now() - timedelta(days=days)

        # 删除过期记录
        stmt = delete(GlobalInsights).where(
            GlobalInsights.date < cutoff_date.strftime("%Y-%m-%d")
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount


# Sqlalchemy 模型


class GlobalInsights(Model):
    __tablename__ = "suggarchat_global_insights"
    date: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: datetime.now().strftime("%Y-%m-%d"),
    )
    token_input: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0")
    )
    token_output: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0")
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0)


class Memory(Model):
    __tablename__ = "suggarchat_memory_data"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ins_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_group: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    memory_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=MemoryModel().model_dump(),
        nullable=False,
        server_default=text("'{}'"),
    )
    sessions_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=[],
        nullable=False,
        server_default=text("'[]'"),
    )
    time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    input_token_usage: Mapped[int] = mapped_column(BigInteger, default=0)
    output_token_usage: Mapped[int] = mapped_column(BigInteger, default=0)
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
        BigInteger,
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
    async with database_lock(ins_id, is_group):
        stmt = select(Memory).where(
            Memory.ins_id == ins_id, Memory.is_group == is_group
        )
        stmt = stmt.with_for_update() if for_update else stmt
        result = await session.execute(stmt)
        if not (memory := result.scalar_one_or_none()):
            stmt = insert(Memory).values(ins_id=ins_id, is_group=is_group)
            await session.execute(stmt)
            await session.commit()
            stmt = select(Memory).where(
                Memory.ins_id == ins_id, Memory.is_group == is_group
            )
            stmt = stmt.with_for_update() if for_update else stmt
            memory = (await session.execute(stmt)).scalar_one()
        session.add(memory)
        if not is_group:
            return memory
        stmt = select(GroupConfig).where(GroupConfig.group_id == ins_id)
        stmt = stmt.with_for_update() if for_update else stmt
        result = await session.execute(stmt)
        if not (group_config := result.scalar_one_or_none()):
            stmt = insert(GroupConfig).values(group_id=ins_id)
            await session.execute(stmt)
            await session.commit()
            stmt = select(GroupConfig).where(GroupConfig.group_id == ins_id)
            group_config = (await session.execute(stmt)).scalar_one()
        session.add(group_config)
        return group_config, memory
