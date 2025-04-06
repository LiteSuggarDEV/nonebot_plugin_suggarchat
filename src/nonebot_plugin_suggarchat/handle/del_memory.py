from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher

from ..config import config_manager
from ..resources import get_memory_data, write_memory_data


async def del_memory(bot: Bot, event: MessageEvent, matcher: Matcher):
    """处理删除记忆指令"""
    # 检查配置以确定是否启用功能
    if not config_manager.config.enable:
        matcher.skip()

    # 判断事件是否来自群聊
    if isinstance(event, GroupMessageEvent):
        # 获取群成员信息
        member = await bot.get_group_member_info(
            group_id=event.group_id, user_id=event.user_id
        )

        # 检查用户权限，非管理员且不在管理员列表中的用户将被拒绝
        if (
            member["role"] == "member"
            and event.user_id not in config_manager.config.admins
        ):
            await matcher.send("你没有这样的力量（管理员/管理员+）")
            return

        # 获取群聊记忆数据
        GData = get_memory_data(event)

        # 清除群聊上下文
        if GData["id"] == event.group_id:
            GData["memory"]["messages"] = []
            await matcher.send("上下文已清除")
            write_memory_data(event, GData)
            logger.debug(f"{event.group_id}Memory deleted")

    else:
        # 获取私聊记忆数据
        FData = get_memory_data(event)

        # 清除私聊上下文
        if FData["id"] == event.user_id:
            FData["memory"]["messages"] = []
            await matcher.send("上下文已清除")
            logger.debug(f"{event.user_id}Memory deleted")
            write_memory_data(event, FData)
