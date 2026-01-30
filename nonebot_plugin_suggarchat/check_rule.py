import contextlib
import random
import time

import nonebot
from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import (
    Event,
    GroupMessageEvent,
    MessageEvent,
)
from nonebot_plugin_orm import get_session
from typing_extensions import override

from nonebot_plugin_suggarchat.utils.libchat import usage_enough
from nonebot_plugin_suggarchat.utils.lock import get_group_lock, get_private_lock
from nonebot_plugin_suggarchat.utils.models import TextContent

from .config import ConfigManager
from .utils.functions import (
    get_current_datetime_timestamp,
    synthesize_message,
)
from .utils.memory import get_memory_data
from .utils.models import Message, get_or_create_data

nb_config = get_driver().config


class FakeEvent(Event):
    """伪造事件类，用于模拟用户事件"""

    user_id: int

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)


async def is_bot_enabled(event: Event) -> bool:
    if not ConfigManager().config.enable:
        return False
    elif (
        hasattr(event, "group_id")
        and not ConfigManager().config.function.enable_group_chat
    ):
        return False
    else:
        if not ConfigManager().config.function.enable_private_chat:
            return False
    with contextlib.suppress(Exception):
        bots = set(nonebot.get_bots().keys())
        if event.get_user_id() in bots:  # 多实例下防止冲突
            return False
    if getattr(event, "group_id", None) is not None:
        async with get_session() as session:
            data, _ = await get_or_create_data(
                session=session, ins_id=getattr(event, "group_id"), is_group=True
            )
            return data.enable
    return True


async def is_group_admin(event: GroupMessageEvent, bot: Bot) -> bool:
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


async def is_bot_admin(event: Event) -> bool:
    return (int(event.get_user_id())) in ConfigManager().config.admin.admins + [
        int(user) for user in nb_config.superusers if user.isdigit()
    ]


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
        if "at" in ConfigManager().config.autoreply.keywords:  # 如果配置为 at 开头
            if event.is_tome():  # 判断是否 @ 了机器人
                return True
        if ConfigManager().config.autoreply.keywords_mode == "starts_with":
            if message_text.startswith(
                tuple(i for i in ConfigManager().config.autoreply.keywords if i != "at")
            ):
                return True
        elif ConfigManager().config.autoreply.keywords_mode == "contains":
            if any(
                keyword in message_text
                for keyword in ConfigManager().config.autoreply.keywords
                if keyword != "at"
            ):
                return True

        # 判断是否启用了AutoReply模式
        if ConfigManager().config.autoreply.enable:
            # 根据概率决定是否回复
            rand = random.random()
            rate = ConfigManager().config.autoreply.probability

            # 获取记忆数据
            memory_data = await get_memory_data(event)
            if rand <= rate and (
                ConfigManager().config.autoreply.global_enable
                or memory_data.fake_people
            ):
                memory_data.timestamp = time.time()
                await memory_data.save(event)
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
                if not ConfigManager().config.function.use_user_nickname
                else event.sender.nickname
            )

            # 生成消息内容并记录到记忆
            content_message = f"[{role}][{Date}][{user_name}（{user_id}）]说:{content}"
            if (
                not len(memory_data.memory.messages) > 1
                or memory_data.memory.messages[-1].role != "user"
                or (not memory_data.memory.messages[-1].content)
            ):
                memory_data.memory.messages.append(
                    Message(
                        role="user",
                        content=[TextContent(type="text", text=content_message)],
                    )
                )
            elif isinstance(memory_data.memory.messages[-1].content, str):
                memory_data.memory.messages[-1].content = [
                    TextContent(
                        type="text", text=str(memory_data.memory.messages[-1].content)
                    ),
                    TextContent(type="text", text=content_message),
                ]
            else:
                assert isinstance(memory_data.memory.messages[-1].content, list)
                if len(memory_data.memory.messages[-1].content) >= 100:
                    memory_data.memory.messages[
                        -1
                    ].content = memory_data.memory.messages[-1].content[-100:]
                memory_data.memory.messages[-1].content.append(
                    TextContent(type="text", text=content_message)
                )
            # 写入记忆数据
            await memory_data.save(event)

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
                    await bot.send(event, "今天的聊天额度已经用完了～")
                    return False
            return False
        return True
    return False
