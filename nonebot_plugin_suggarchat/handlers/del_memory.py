from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot_plugin_amrita import CachedUserDataRepository

from ..utils.sql import get_uni_user_id


async def del_memory(event: MessageEvent, matcher: Matcher):
    """清空当前记忆"""
    repo = CachedUserDataRepository()
    data = await repo.get_memory(get_uni_user_id(event))
    data.memory_json.messages.clear()
    await repo.update_memory_data(data)
    await matcher.send("上下文已清除")
