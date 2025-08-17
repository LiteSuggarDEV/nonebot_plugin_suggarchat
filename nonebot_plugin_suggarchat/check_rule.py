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

from .config import config_manager
from .utils.functions import (
    get_current_datetime_timestamp,
    synthesize_message,
)
from .utils.memory import Message, get_memory_data

nb_config = get_driver().config


async def is_bot_enabled(event: Event) -> bool:
    if not config_manager.config.enable:
        return False
    with contextlib.suppress(Exception):
        bots = set(nonebot.get_bots().keys())
        if event.get_user_id() in bots:  # 多实例下防止冲突
            return False
    if hasattr(event, "group_id"):
        data = await get_memory_data(event)
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
    return (int(event.get_user_id())) in config_manager.config.admin.admins + [
        int(user) for user in nb_config.superusers if user.isdigit()
    ]


async def is_group_admin_if_is_in_group(event: MessageEvent, bot: Bot) -> bool:
    if isinstance(event, GroupMessageEvent):
        return await is_group_admin(event, bot)
    return True


async def should_respond_to_message(event: MessageEvent, bot: Bot) -> bool:
    """根据配置和消息事件判断是否需要回复"""

    message = event.get_message()
    message_text = message.extract_plain_text().strip()

    # 如果不是群聊消息，直接返回 True
    if not isinstance(event, GroupMessageEvent):
        return True

    # 判断是否以关键字触发回复
    if "at" in config_manager.config.autoreply.keywords:  # 如果配置为 at 开头
        if event.is_tome():  # 判断是否 @ 了机器人
            return True
    elif any(
        message_text.startswith(kw)
        for kw in config_manager.config.autoreply.keywords
        if kw != "at"
    ):  # 如果消息以关键字开头
        return True

    # 判断是否启用了AutoReply模式
    if config_manager.config.autoreply.enable:
        # 根据概率决定是否回复
        rand = random.random()
        rate = config_manager.config.autoreply.probability

        # 获取记忆数据
        memory_data = await get_memory_data(event)
        if rand <= rate and (
            config_manager.config.autoreply.global_enable or memory_data.fake_people
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
            (await bot.get_group_member_info(group_id=event.group_id, user_id=user_id))[
                "nickname"
            ]
            if not config_manager.config.function.use_user_nickname
            else event.sender.nickname
        )

        # 生成消息内容并记录到记忆
        content_message = f"[{role}][{Date}][{user_name}（{user_id}）]说:{content}"
        fwd_msg = Message(role="user", content="<FORWARD_MSG>\n" + content_message)
        message_l = memory_data.memory.messages
        if not message_l:
            message_l.append(fwd_msg)
        elif not isinstance(message_l[-1].content, str) or message_l[-1].role != "user":
            message_l.append(fwd_msg)
        elif not message_l[-1].content.startswith("<FORWARD_MSG>"):
            message_l.append(fwd_msg)
        else:
            message_l[-1].content += "\n" + content_message
        if len(
            message_l[-1].content
        ) > config_manager.config.llm_config.memory_lenth_limit * 10 and isinstance(
            message_l[-1].content, str
        ):
            lines = message_l[-1].content.splitlines(keepends=True)
            if len(lines) >= 2:
                # 删除索引为1的第二行
                del lines[1]
            message_l[-1].content = "".join(lines)
        memory_data.memory.messages = message_l

        # 写入记忆数据
        await memory_data.save(event)

    # 默认返回 False
    return False
