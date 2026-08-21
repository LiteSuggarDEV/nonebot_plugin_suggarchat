from nonebot import logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.matcher import Matcher

from ..utils.app import CachedGroupDataRepository


async def _set_chat(event: GroupMessageEvent, matcher: Matcher, on: bool) -> None:
    """开启/关闭群聊"""
    repo = CachedGroupDataRepository()
    group_config = await repo.get_group_config(event.group_id)
    group_config.enable = on
    await repo.update_group_config(group_config)
    logger.debug(f"{event.group_id} {'enabled' if on else 'disabled'}")
    await matcher.send("✅ 已启用聊天功能" if on else "已禁用聊天功能")


async def disable(event: GroupMessageEvent, matcher: Matcher):
    """禁用群聊聊天功能"""
    await _set_chat(event, matcher, False)
