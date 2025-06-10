from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher

from ..utils import get_memory_data, write_memory_data


async def disable(bot: Bot, event: GroupMessageEvent, matcher: Matcher):
    """处理禁用聊天功能的异步函数"""

    # 记录禁用操作日志
    logger.debug(f"{event.group_id} disabled")

    # 获取并更新群聊状态数据
    data = get_memory_data(event)
    if data["id"] == event.group_id:
        if not data["enable"]:
            await matcher.send("聊天功能已禁用")
        else:
            data["enable"] = False
            await matcher.send("聊天功能已成功禁用")

    # 保存更新后的群聊状态数据
    write_memory_data(event, data)
