from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.matcher import Matcher

from ..utils.memory import get_memory_data


async def disable(bot: Bot, event: GroupMessageEvent, matcher: Matcher):
    """处理禁用聊天功能的异步函数"""
    # 记录禁用操作日志
    logger.debug(f"{event.group_id} disabled")

    # 获取并更新群聊状态数据
    data = await get_memory_data(event)
    data.enable = False
    await data.save(event)
    await matcher.send("聊天功能已禁用")

    # 保存更新后的群聊状态数据
