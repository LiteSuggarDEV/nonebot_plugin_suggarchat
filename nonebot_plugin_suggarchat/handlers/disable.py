from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.matcher import Matcher

from ..check_rule import is_bot_admin
from ..utils.memory import get_memory_data, write_memory_data


async def disable(bot: Bot, event: GroupMessageEvent, matcher: Matcher):
    """处理禁用聊天功能的异步函数"""
    if not await is_bot_admin(event, bot):
        await matcher.finish("你没有权限禁用聊天功能")
    # 记录禁用操作日志
    logger.debug(f"{event.group_id} disabled")

    # 获取并更新群聊状态数据
    data = await get_memory_data(event)
    if data["id"] == event.group_id:
        if data["enable"]:
            data["enable"] = False
        await matcher.send("聊天功能已禁用")

    # 保存更新后的群聊状态数据
    await write_memory_data(event, data)
