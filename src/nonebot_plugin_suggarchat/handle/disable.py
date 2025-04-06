from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher

from ..config import config_manager
from ..resources import get_memory_data, write_memory_data


async def disable(bot: Bot, event: GroupMessageEvent, matcher: Matcher):
    """处理禁用聊天功能的异步函数"""
    if not config_manager.config.enable:
        matcher.skip()

    # 获取发送消息的成员信息
    member = await bot.get_group_member_info(
        group_id=event.group_id, user_id=event.user_id
    )

    # 检查成员是否为普通成员且不在管理员列表中，如果是则发送提示消息并返回
    if member["role"] == "member" and event.user_id not in config_manager.config.admins:
        await matcher.send("你没有这样的力量呢～（管理员/管理员+）")
        return

    # 记录禁用操作的日志
    logger.debug(f"{event.group_id} disabled")

    # 获取并更新记忆中的数据结构
    data = get_memory_data(event)
    if data["id"] == event.group_id:
        if not data["enable"]:
            await matcher.send("聊天禁用")
        else:
            data["enable"] = False
            await matcher.send("聊天已经禁用")

    # 将更新后的数据结构写回记忆
    write_memory_data(event, data)
