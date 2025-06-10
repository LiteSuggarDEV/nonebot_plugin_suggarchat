import random
import time

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent,
    MessageEvent,
)

from .config import config_manager
from .utils import (
    get_current_datetime_timestamp,
    get_memory_data,
    synthesize_message,
    write_memory_data,
)


async def is_bot_enabled() -> bool:
    return config_manager.config.enable


async def is_group_admin(event: GroupMessageEvent, bot: Bot) -> bool:
    is_admin: bool = False
    try:
        role: str = (
            await bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id
            )
        )["role"]
        if role != "member" or event.user_id in config_manager.config.admins:
            is_admin = True
    except Exception:
        logger.warning(f"获取群成员信息失败: {event.group_id} {event.user_id}")
    return is_admin


async def is_bot_admin(event: MessageEvent, bot: Bot) -> bool:
    return event.user_id in config_manager.config.admins


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
    if config_manager.config.keyword == "at":  # 如果配置为 at 开头
        if event.is_tome():  # 判断是否 @ 了机器人
            return True
    elif message_text.startswith(config_manager.config.keyword):  # 如果消息以关键字开头
        return True

    # 判断是否启用了伪装人模式
    if config_manager.config.fake_people:

        # 根据概率决定是否回复
        rand = random.random()
        rate = config_manager.config.probability

        # 获取内存数据
        memory_data: dict = get_memory_data(event)
        if rand <= rate and (
            config_manager.config.global_fake_people
            or memory_data.get("fake_people", False)
        ):
            memory_data["timestamp"] = time.time()
            write_memory_data(event, memory_data)
            return True
        # 合成消息内容
        content = await synthesize_message(message, bot)

        # 获取当前时间戳
        Date = get_current_datetime_timestamp()

        # 获取用户角色信息
        role = (
            await bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id
            )
        )["role"]
        if role == "admin":
            role = "群管理员"
        elif role == "owner":
            role = "群主"
        elif role == "member":
            role = "普通成员"

        # 获取用户 ID 和昵称
        user_id = event.user_id
        user_name = (
            await bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id
            )
        )["nickname"]

        # 生成消息内容并记录到内存
        content_message = f"[{role}][{Date}][{user_name}（{user_id}）]说:{content}"
        fwd_msg = {"role": "user", "content": "<FORWARD_MSG>\n" + content_message}
        message_l = memory_data["memory"]["messages"]  # type: list[dict[str, str]]
        if not message_l:
            message_l.append(fwd_msg)
        elif (
            not isinstance(message_l[-1].get("content"), str)
            or message_l[-1]["role"] != "user"
        ):
            message_l.append(fwd_msg)
        elif not message_l[-1]["content"].startswith("<FORWARD_MSG>"):
            message_l.append(fwd_msg)
        else:
            message_l[-1]["content"] += "\n" + content_message
        if len(message_l[-1]["content"]) > 1500:
            lines = message_l[-1]["content"].splitlines(keepends=True)
            if len(lines) >= 2:
                # 删除索引为1的第二行
                del lines[1]
            message_l[-1]["content"] = "".join(lines)
        memory_data["memory"]["messages"] = message_l

        # 写入内存数据
        write_memory_data(event, memory_data)

    # 默认返回 False
    return False
