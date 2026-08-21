"""本地三级权限规则

- SUPERUSER：``user_id in get_driver().config.superusers``
- 群管理：群主/群管理员，或 SUPERUSER
- 普通用户：其他
"""

from __future__ import annotations

import contextlib
import random
import time

import nonebot
from amrita_core.types import Message, TextContent
from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import (
    Event,
    GroupMessageEvent,
    MessageEvent,
)
from nonebot_plugin_amrita.memory import MemorySchema
from typing_extensions import override

from .config import config_manager
from .utils.data_access import get_group_config, get_memory, update_memory
from .utils.functions import (
    get_current_datetime_timestamp,
    synthesize_message,
)
from .utils.libchat import usage_enough
from .utils.lock import get_group_lock, get_private_lock
from .utils.sql import make_uni_id

nb_config = get_driver().config


class FakeEvent(Event):
    """伪事件类，用于模拟用户事件"""

    user_id: int

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


async def is_bot_globally_enabled(event: Event) -> bool:
    """仅检查全局开关与功能开关，不检查每群的 enable 标记。

    供聊天开关（/chat）等命令使用，避免 /chat off 关闭群聊后
    is_bot_enabled 失效，导致无法再次执行 /chat on。
    """
    gid = getattr(event, "group_id", None)
    is_in_group = gid is not None
    if not config_manager.config.enable:
        return False
    elif is_in_group and not config_manager.config.function.enable_group_chat:
        return False
    elif not is_in_group and not config_manager.config.function.enable_private_chat:
        return False
    with contextlib.suppress(Exception):
        bots = nonebot.get_bots()
        if event.get_user_id() in bots:
            return False
    return True


async def is_bot_enabled(event: Event) -> bool:
    gid = getattr(event, "group_id", None)
    if not await is_bot_globally_enabled(event):
        return False
    if gid is not None:
        data = await get_group_config(gid)
        return data.enable
    return True


async def is_bot_admin(event: Event) -> bool:
    """SUPERUSER 判定：user_id 是否在全局 superusers 中"""
    return event.get_user_id() in get_driver().config.superusers


async def is_group_admin(event: GroupMessageEvent, bot: Bot) -> bool:
    """群管理判定：群主/群管理员，或 SUPERUSER"""
    try:
        role: str = (
            (
                await bot.get_group_member_info(
                    group_id=event.group_id, user_id=event.user_id
                )
            )["role"]
            if not event.sender.role
            else event.sender.role
        )
        if role != "member":
            return True
        if await is_bot_admin(event):
            return True
    except Exception:
        logger.warning(f"获取群成员信息失败: {event.group_id} {event.user_id}")
    return False


async def is_group_admin_if_is_in_group(event: MessageEvent, bot: Bot) -> bool:
    if isinstance(event, GroupMessageEvent):
        return await is_group_admin(event, bot)
    return True


async def should_respond_to_message(event: MessageEvent, bot: Bot) -> bool:
    """根据配置和消息事件判断是否需要回复"""
    lock = (
        get_group_lock(event.group_id)
        if isinstance(event, GroupMessageEvent)
        else get_private_lock(event.user_id)
    )
    async with lock:
        message = event.get_message()
        message_text = message.extract_plain_text().strip()
        if not isinstance(event, GroupMessageEvent):
            return True

        # 判断是否以关键字触发回复
        if "at" in config_manager.config.autoreply.keywords:  # 如果配置为 at 开头
            if event.is_tome():  # 判断是否 @ 了机器人
                return True
        if config_manager.config.autoreply.keywords_mode == "starts_with":
            if message_text.startswith(
                tuple(i for i in config_manager.config.autoreply.keywords if i != "at")
            ):
                return True
        elif config_manager.config.autoreply.keywords_mode == "contains":
            if any(
                keyword in message_text
                for keyword in config_manager.config.autoreply.keywords
                if keyword != "at"
            ):
                return True

        # 判断是否启用了AutoReply模式
        if config_manager.config.autoreply.enable:
            # 根据概率决定是否回复
            rand = random.random()
            rate = config_manager.config.autoreply.probability

            # 获取记忆数据
            is_group = bool(getattr(event, "group_id", None))
            ins_id: int = getattr(event, "group_id", event.user_id)
            memory_data: MemorySchema = await get_memory(make_uni_id(ins_id, is_group))
            fk = (await get_group_config(ins_id)).autoreply

            if rand <= rate and (config_manager.config.autoreply.global_enable or fk):
                memory_data.memory_json.time = time.time()
                await update_memory(memory_data)
                return True
            # 合成消息内容
            content = await synthesize_message(message, bot)

            # 获取当前时间戳
            Date = get_current_datetime_timestamp()

            # 获取用户角色信息
            role = (
                (
                    await bot.get_group_member_info(
                        group_id=event.group_id, user_id=event.user_id
                    )
                )
                if not event.sender.role
                else event.sender.role
            )
            if role == "admin":
                role = "群管理员"
            elif role == "owner":
                role = "群主"
            elif role == "member":
                role = "普通成员"

            # 获取用户 ID 和昵称
            user_id = event.user_id
            user_name = (
                (
                    await bot.get_group_member_info(
                        group_id=event.group_id, user_id=user_id
                    )
                )["nickname"]
                if not config_manager.config.function.use_user_nickname
                else event.sender.nickname
            )

            # 生成消息内容并记录到记忆
            content_message = f"[{role}][{Date}][{user_name}（{user_id}）]说:{content}"
            if (
                not len(memory_data.memory_json.messages) > 1
                or memory_data.memory_json.messages[-1].role != "user"
                or (not memory_data.memory_json.messages[-1].content)
            ):
                memory_data.memory_json.messages.append(
                    Message(
                        role="user",
                        content=[TextContent(type="text", text=content_message)],
                    )
                )
            elif isinstance(memory_data.memory_json.messages[-1].content, str):
                memory_data.memory_json.messages[-1].content = [
                    TextContent(
                        type="text",
                        text=str(memory_data.memory_json.messages[-1].content),
                    ),
                    TextContent(type="text", text=content_message),
                ]
            else:
                assert isinstance(memory_data.memory_json.messages[-1].content, list)
                if len(memory_data.memory_json.messages[-1].content) >= 100:
                    memory_data.memory_json.messages[
                        -1
                    ].content = memory_data.memory_json.messages[-1].content[-100:]
                memory_data.memory_json.messages[-1].content.append(
                    TextContent(type="text", text=content_message)
                )
            await update_memory(memory_data)
        # 默认返回 False
        return False


async def should_respond_with_usage_check(event: MessageEvent, bot: Bot) -> bool:
    if await should_respond_to_message(event, bot):
        if not await usage_enough(event) or not (
            await usage_enough(
                FakeEvent(time=0, self_id=0, post_type="", user_id=event.user_id)
            )
            if isinstance(event, GroupMessageEvent)
            else True
        ):
            if event.is_tome():
                with contextlib.suppress(Exception):
                    await bot.send(
                        event,
                        random.choice(config_manager.config.usage_limit.limit_msg),
                    )
                    return False
            return False
        return True
    return False
