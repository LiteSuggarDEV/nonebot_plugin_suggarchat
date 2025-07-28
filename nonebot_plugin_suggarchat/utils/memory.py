import asyncio
import json
import time
from pathlib import Path
from typing import Any

import aiofiles
from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Event,
    GroupMessageEvent,
    PokeNotifyEvent,
    PrivateMessageEvent,
)
from pydantic import BaseModel, Field

from ..chatmanager import chat_manager
from ..config import config_manager
from .functions import convert_to_utf8


class Memory(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)


class MemoryModel(BaseModel, extra="allow"):
    id: int = Field(..., description="ID")
    enable: bool = Field(default=True, description="是否启用")
    memory: Memory = Field(default=Memory(), description="记忆")
    full: bool = Field(default=False, description="是否启用Fullmode")
    sessions: list[dict[str, Any]] = Field(default=[], description="会话")
    timestamp: float = Field(default=time.time(), description="时间戳")
    fake_people: bool = Field(default=False, description="是否启用假人")
    prompt: str = Field(default="", description="用户自定义提示词")

    def __str__(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=True)

    def __repr__(self) -> str:
        return self.__str__()

    def __getitem__(self, key: str) -> Any:
        return self.model_dump()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.__setattr__(key, value)


write_read_lock: asyncio.Lock = asyncio.Lock()


async def get_memory_data(event: Event) -> MemoryModel:
    """获取事件对应的记忆数据，如果不存在则创建初始数据"""
    if chat_manager.debug:
        logger.debug(f"获取{event.get_type()} {event.get_session_id()} 的记忆数据")
    private_memory = config_manager.private_memory
    group_memory = config_manager.group_memory
    conf_path: None | Path = None
    async with write_read_lock:
        Path.mkdir(private_memory, exist_ok=True)
        Path.mkdir(group_memory, exist_ok=True)

        if (
            not isinstance(event, PrivateMessageEvent)
            and not isinstance(event, GroupMessageEvent)
            and isinstance(event, PokeNotifyEvent)
            and event.group_id
        ) or (
            not isinstance(event, PrivateMessageEvent)
            and isinstance(event, GroupMessageEvent)
            and event.group_id
        ):
            group_id: int = event.group_id
            conf_path = Path(group_memory / f"{group_id}.json")
            if not conf_path.exists():
                async with aiofiles.open(
                    str(conf_path),
                    "w",
                ) as f:
                    await f.write(str(MemoryModel(id=group_id)))
        elif (
            not isinstance(event, PrivateMessageEvent)
            and isinstance(event, PokeNotifyEvent)
        ) or isinstance(event, PrivateMessageEvent):
            user_id = event.user_id
            conf_path = Path(private_memory / f"{user_id}.json")
            if not conf_path.exists():
                async with aiofiles.open(
                    str(conf_path),
                    "w",
                ) as f:
                    await f.write(str(MemoryModel(id=user_id)))
        assert conf_path is not None, "conf_path is None"
        convert_to_utf8(conf_path)
        async with aiofiles.open(
            str(conf_path),
        ) as f:
            conf = MemoryModel(**json.loads(await f.read()))
            if chat_manager.debug:
                logger.debug(f"读取到记忆数据{conf}")
            return conf


async def write_memory_data(event: Event, data: MemoryModel) -> None:
    """将记忆数据写入对应的文件"""
    if chat_manager.debug:
        logger.debug(f"写入记忆数据{data.model_dump_json()}")
        logger.debug(f"事件：{type(event)}")
    group_memory = config_manager.group_memory
    private_memory = config_manager.private_memory
    conf_path = None
    async with write_read_lock:
        if isinstance(event, GroupMessageEvent):
            group_id = event.group_id
            conf_path = Path(group_memory / f"{group_id}.json")
        elif isinstance(event, PrivateMessageEvent):
            user_id = event.user_id
            conf_path = Path(private_memory / f"{user_id}.json")
        elif isinstance(event, PokeNotifyEvent):
            if event.group_id:
                group_id = event.group_id
                conf_path = Path(group_memory / f"{group_id}.json")
                if not conf_path.exists():
                    async with aiofiles.open(
                        str(conf_path),
                        "w",
                    ) as f:
                        await f.write(
                            str(
                                MemoryModel(
                                    id=group_id,
                                )
                            )
                        )
            else:
                user_id = event.user_id
                conf_path = Path(private_memory / f"{user_id}.json")
                if not conf_path.exists():
                    async with aiofiles.open(
                        str(conf_path),
                        "w",
                    ) as f:
                        await f.write(
                            str(
                                MemoryModel(
                                    id=user_id,
                                )
                            )
                        )
        assert conf_path is not None
        async with aiofiles.open(
            str(conf_path),
            "w",
        ) as f:
            await f.write(str(data.model_dump_json()))
