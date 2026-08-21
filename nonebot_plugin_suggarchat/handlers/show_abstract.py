from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot_plugin_amrita import CachedUserDataRepository

from ..utils.sql import get_uni_user_id


async def abstract_show(event: MessageEvent, matcher: Matcher):
    """查看当前会话摘要"""
    repo = CachedUserDataRepository()
    data = await repo.get_memory(get_uni_user_id(event))
    await matcher.send(
        f"当前对话上下文摘要：\n{str(data.memory_json.abstract) or '无'}"
    )
    data.clean()
