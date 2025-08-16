from __future__ import annotations

import json
import time
import typing
from datetime import datetime
from typing import Any, Literal, overload

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Event,
)
from nonebot_plugin_orm import AsyncSession, get_session
from pydantic import BaseModel as Model
from pydantic import Field

from ..chatmanager import chat_manager
from .sql_models import get_or_create_data


class BaseModel(Model):
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


class Memory(BaseModel):
    messages: list[Message | ToolResult] = Field(default_factory=list)
    time: float = Field(default_factory=time.time, description="时间戳")


class MemoryModel(BaseModel, extra="allow"):
    enable: bool = Field(default=True, description="是否启用")
    memory: Memory = Field(default=Memory(), description="记忆")
    sessions: list[Memory] = Field(default_factory=list, description="会话")
    timestamp: float = Field(default=time.time(), description="时间戳")
    fake_people: bool = Field(default=False, description="是否启用假人")
    prompt: str = Field(default="", description="用户自定义提示词")
    usage: int = Field(default=0, description="请求次数")

    async def save(self, event: Event, session: AsyncSession | None = None) -> None:
        """保存当前记忆数据到文件"""
        if session is None:
            session = get_session()

        await write_memory_data(event, self, session)


@overload
async def get_memory_data(*, user_id: int) -> MemoryModel: ...


@overload
async def get_memory_data(*, group_id: int) -> MemoryModel: ...


@overload
async def get_memory_data(event: Event) -> MemoryModel: ...


async def get_memory_data(
    event: Event | None = None,
    *,
    user_id: int | None = None,
    group_id: int | None = None,
) -> MemoryModel:
    """获取事件对应的记忆数据，如果不存在则创建初始数据"""
    is_group = False
    if ins_id := (getattr(event, "group_id", None) or group_id):
        if chat_manager.debug:
            logger.debug(f"获取Group{group_id} 的记忆数据")
        ins_id = typing.cast(int, group_id)
        is_group = True
    else:
        ins_id = typing.cast(int, event.get_user_id()) if event else user_id
        assert ins_id is not None, "User id is None!"
        if chat_manager.debug:
            logger.debug(f"获取用户{user_id}的记忆数据")
    async with get_session() as session:
        group_conf = None
        if is_group:
            group_conf, memory = await get_or_create_data(
                session=session,
                ins_id=ins_id,
                is_group=is_group,
            )

            session.add(group_conf)

        else:
            memory = await get_or_create_data(session=session, ins_id=ins_id)

        session.add(memory)
        messages = [
            (
                Message.model_validate(i)
                if i["role"] != "tool"
                else ToolResult.model_validate(i)
            )
            for i in json.loads(memory.messages_json)
        ]
        c_memory = Memory(messages=messages, time=memory.time.timestamp())

        sessions = [Memory.model_validate(i) for i in json.loads(memory.sessions_json)]
        conf = MemoryModel(
            memory=c_memory,
            sessions=sessions,
            usage=memory.usage_count,
            timestamp=memory.time.timestamp(),
        )
        if group_conf:
            conf.enable = group_conf.enable
            conf.fake_people = group_conf.fake_people
            conf.prompt = group_conf.prompt
        if (
            datetime.fromtimestamp(conf.timestamp).date().isoformat()
            != datetime.now().date().isoformat()
        ):
            conf.usage = 0
            conf.timestamp = int(datetime.now().timestamp())
            if event:
                await conf.save(event, session)
    if chat_manager.debug:
        logger.debug(f"读取到记忆数据{conf}")

    return conf


async def write_memory_data(
    event: Event, data: MemoryModel, session: AsyncSession
) -> None:
    """将记忆数据写入对应的文件"""
    if chat_manager.debug:
        logger.debug(f"写入记忆数据{data.model_dump_json()}")
        logger.debug(f"事件：{type(event)}")
    is_group = hasattr(event, "group_id")
    ins_id = int(getattr(event, "group_id") if is_group else event.get_user_id())
    async with session.begin():
        group_conf = None
        if is_group:
            group_conf, memory = await get_or_create_data(
                session=session,
                ins_id=ins_id,
                is_group=is_group,
                for_update=True,
            )

            session.add(group_conf)

        else:
            memory = await get_or_create_data(
                session=session,
                ins_id=ins_id,
                for_update=True,
            )
        session.add(memory)
        memory.messages_json = data.memory.model_dump_json()
        memory.sessions_json = json.dumps([s.model_dump() for s in data.sessions])
        memory.time = datetime.fromtimestamp(data.timestamp)
        memory.usage_count = data.usage

        if group_conf:
            group_conf.enable = data.enable
            group_conf.prompt = data.prompt
            group_conf.fake_people = data.fake_people
            group_conf.last_updated = datetime.now()
        await session.commit()
