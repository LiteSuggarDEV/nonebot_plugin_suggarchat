from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher

from ..check_rule import is_group_admin_if_is_in_group
from ..utils.memory import get_memory_data, write_memory_data


async def del_memory(bot: Bot, event: MessageEvent, matcher: Matcher):
    """处理删除记忆的指令"""
    if not await is_group_admin_if_is_in_group(event, bot):
        return
    data = await get_memory_data(event)

    if isinstance(event, GroupMessageEvent):
        # 清除群聊上下文
        if event.group_id == data["id"]:
            data["memory"]["messages"] = []
    elif event.user_id == data["id"]:
        data["memory"]["messages"] = []

    await matcher.send("上下文已清除")
    await write_memory_data(event, data)
    logger.info(
        f"{event.get_event_name()}:{getattr(event, 'group_id') if hasattr(event, 'group_id') else event.user_id} 的记忆已清除"
    )
