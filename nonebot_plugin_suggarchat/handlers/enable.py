from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.matcher import Matcher

from ..utils.memory import get_memory_data


async def enable(bot: Bot, event: GroupMessageEvent, matcher: Matcher):
    """处理启用聊天功能的命令"""

    # 记录日志
    logger.debug(f"{event.group_id} enabled")
    # 获取当前群组的记忆数据
    data = await get_memory_data(event)
    # 检查记忆数据是否与当前群组匹配
    data.enable = True
    await data.save(event)
    await matcher.send("已启用聊天功能")
