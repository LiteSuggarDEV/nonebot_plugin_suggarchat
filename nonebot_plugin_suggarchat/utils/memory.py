from __future__ import annotations

import time
from datetime import datetime
from typing import overload

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Event,
)
from nonebot_plugin_orm import AsyncSession, get_session
from pydantic import Field

from ..chatmanager import chat_manager
from .models import (
    BaseModel,
    Message,
    ToolResult,
    get_or_create_data,
)
from .models import (
    MemoryModel as Memory,
)


class MemoryModel(BaseModel, extra="allow"):
    enable: bool = Field(default=True, description="是否启用")
    memory: Memory = Field(default=Memory(), description="记忆")
    sessions: list[Memory] = Field(default_factory=list, description="会话")
    timestamp: float = Field(default=time.time(), description="时间戳")
    fake_people: bool = Field(default=False, description="是否启用假人")
    prompt: str = Field(default="", description="用户自定义提示词")
    usage: int = Field(default=0, description="请求次数")
    input_token_usage: int = Field(default=0, description="token使用量")
    output_token_usage: int = Field(default=0, description="token使用量")

    async def save(
        self,
        event: Event,
        *,
        raise_err: bool = True,
    ) -> None:
        """保存当前记忆数据到文件"""

        session = get_session()

        async with session:
            await write_memory_data(event, self, session, raise_err)


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
    if (ins_id := (getattr(event, "group_id", None) or group_id)) is not None:
        ins_id = int(ins_id)
        if chat_manager.debug:
            logger.debug(f"获取Group{ins_id} 的记忆数据")
        is_group = True
    else:
        ins_id = int(event.get_user_id()) if event else user_id
        if chat_manager.debug:
            logger.debug(f"获取用户{ins_id}的记忆数据")
    assert ins_id is not None, "Ins_id is None!"
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
        await session.refresh(memory)
        memory_data = memory.memory_json
        sessions_data = memory.sessions_json
        messages = [
            (
                Message.model_validate(i)
                if i["role"] != "tool"
                else ToolResult.model_validate(i)
            )
            for i in (memory_data)["messages"]
        ]
        c_memory = Memory(messages=messages, time=memory.time.timestamp())

        sessions = [Memory.model_validate(i) for i in sessions_data]
        conf = MemoryModel(
            memory=c_memory,
            sessions=sessions,
            usage=memory.usage_count,
            timestamp=memory.time.timestamp(),
            input_token_usage=memory.input_token_usage,
            output_token_usage=memory.output_token_usage,
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
            conf.input_token_usage = 0
            conf.output_token_usage = 0
            conf.timestamp = int(datetime.now().timestamp())
            if event:
                await conf.save(event)
    if chat_manager.debug:
        logger.debug(f"读取到记忆数据{conf}")

    return conf


async def write_memory_data(
    event: Event,
    data: MemoryModel,
    session: AsyncSession,
    raise_err: bool,
) -> None:
    """将记忆数据写入对应的文件"""
    async with session:
        try:
            if chat_manager.debug:
                logger.debug(f"写入记忆数据{data.model_dump_json()}")
                logger.debug(f"事件：{type(event)}")
            is_group = hasattr(event, "group_id")
            ins_id = int(
                getattr(event, "group_id")
                if is_group and getattr(event, "group_id", None)
                else event.get_user_id()
            )

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
            memory.memory_json = data.memory.model_dump()
            memory.sessions_json = [s.model_dump() for s in data.sessions]
            memory.time = datetime.fromtimestamp(data.timestamp)
            memory.usage_count = data.usage
            memory.input_token_usage = data.input_token_usage
            memory.output_token_usage = data.output_token_usage
            if group_conf:
                group_conf.enable = data.enable
                group_conf.prompt = data.prompt
                group_conf.fake_people = data.fake_people
                group_conf.last_updated = datetime.now()
            await session.commit()
        except Exception as e:
            logger.opt(exception=e, colors=True).error(f"写入记忆数据时出错: {e}")
            await session.rollback()
            if raise_err:
                raise e
