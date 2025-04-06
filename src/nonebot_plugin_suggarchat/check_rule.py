import random

from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)

from nonebot_plugin_suggarchat.config import config_manager
from nonebot_plugin_suggarchat.resources import (
    get_current_datetime_timestamp,
    get_memory_data,
    synthesize_message,
    write_memory_data,
)


async def should_respond_to_message(event: MessageEvent, bot: Bot) -> bool:
    """根据配置和消息事件判断是否触发回复的规则"""

    message = event.get_message()
    message_text = message.extract_plain_text().strip()

    if not isinstance(event, GroupMessageEvent):
        return True

    if config_manager.config.keyword == "at":  # at开头
        if event.is_tome():
            return True
    elif message_text.startswith(config_manager.config.keyword):  # 以关键字开头
        """开头为{keyword}必定回复"""
        return True

    if config_manager.config.fake_people:  # 伪装人
        if event.is_tome() and isinstance(event, PrivateMessageEvent):
            """私聊过滤"""
            return False

        rand = random.random()
        rate = config_manager.config.probability
        if rand <= rate:
            return True

        memory_data: dict = get_memory_data(event)

        # 读取内存数据
        content = await synthesize_message(message, bot)

        Date = get_current_datetime_timestamp()  # 获取当前时间戳

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

        user_id = event.user_id
        user_name = (
            await bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id
            )
        )["nickname"]

        content_message = f"[{role}][{Date}][{user_name}（{user_id}）]说:{content}"

        memory_data["memory"]["messages"].append(
            {"role": "user", "content": content_message}
        )

        write_memory_data(event, memory_data)

    return False
