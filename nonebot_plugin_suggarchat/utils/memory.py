from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

import aiofiles
from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Event,
    GroupMessageEvent,
    PokeNotifyEvent,
    PrivateMessageEvent,
)
from pydantic import BaseModel as Model
from pydantic import Field

from ..chatmanager import chat_manager
from ..config import config_manager
from .functions import convert_to_utf8
from .lock import rw_lock


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
    full: bool = Field(default=False, description="是否启用Fullmode")
    sessions: list[Memory] = Field(default_factory=list, description="会话")
    timestamp: float = Field(default=time.time(), description="时间戳")
    fake_people: bool = Field(default=False, description="是否启用假人")
    prompt: str = Field(default="", description="用户自定义提示词")

    async def save(self, event: Event) -> None:
        """保存当前内存数据到文件"""
        await write_memory_data(event, self)


async def get_memory_data(event: Event) -> MemoryModel:
    """获取事件对应的记忆数据，如果不存在则创建初始数据"""
    async with rw_lock(event):
        if chat_manager.debug:
            logger.debug(f"获取{event.get_type()} {event.get_session_id()} 的记忆数据")
        private_memory = config_manager.private_memory
        group_memory = config_manager.group_memory
        conf_path: None | Path = None
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
                    await f.write(MemoryModel().model_dump_json())
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
                    await f.write(MemoryModel().model_dump_json())
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
    async with rw_lock(event):
        if chat_manager.debug:
            logger.debug(f"写入记忆数据{data.model_dump_json()}")
            logger.debug(f"事件：{type(event)}")
        group_memory = config_manager.group_memory
        private_memory = config_manager.private_memory
        conf_path = None
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
                        await f.write(MemoryModel().model_dump_json())
            else:
                user_id = event.user_id
                conf_path = Path(private_memory / f"{user_id}.json")
                if not conf_path.exists():
                    async with aiofiles.open(
                        str(conf_path),
                        "w",
                    ) as f:
                        await f.write(MemoryModel().model_dump_json())
        assert conf_path is not None
        async with aiofiles.open(
            str(conf_path),
            "w",
        ) as f:
            await f.write(str(data.model_dump_json()))
