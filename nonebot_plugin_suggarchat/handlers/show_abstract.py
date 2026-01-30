from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.matcher import Matcher

from ..check_rule import is_group_admin_if_is_in_group
from ..utils.memory import get_memory_data


async def abstract_show(bot: Bot, event: MessageEvent, matcher: Matcher):
    if not await is_group_admin_if_is_in_group(event, bot):
        return
    data = await get_memory_data(event)
    await matcher.send(f"当前对话上下文摘要：{str(data.memory.abstract) or '无'}")
