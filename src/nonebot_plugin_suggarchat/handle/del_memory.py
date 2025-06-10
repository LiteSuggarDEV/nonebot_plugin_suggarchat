from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher

from ..utils import get_memory_data, write_memory_data


async def del_memory(bot: Bot, event: MessageEvent, matcher: Matcher):
    """处理删除记忆的指令"""

    # 如果是群聊事件
    if isinstance(event, GroupMessageEvent):

        # 获取群聊记忆数据
        GData = get_memory_data(event)

        # 清除群聊上下文
        if GData["id"] == event.group_id:
            GData["memory"]["messages"] = []
            await matcher.send("群聊上下文已清除")
            write_memory_data(event, GData)
            logger.info(f"{event.group_id} 的记忆已清除")

    else:
        # 获取私聊记忆数据
        FData = get_memory_data(event)

        # 清除私聊上下文
        if FData["id"] == event.user_id:
            FData["memory"]["messages"] = []
            await matcher.send("私聊上下文已清除")
            logger.info(f"{event.user_id} 的记忆已清除")
            write_memory_data(event, FData)
