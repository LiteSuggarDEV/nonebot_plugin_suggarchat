from nonebot.adapters.onebot.v11.event import GroupIncreaseNoticeEvent
from nonebot.matcher import Matcher

from ..config import config_manager


async def add_notices(event: GroupIncreaseNoticeEvent, matcher: Matcher):
    """处理群聊增加通知事件"""
    if not config_manager.config.extended.send_msg_after_be_invited:
        return
    if event.user_id == event.self_id:
        await matcher.send(config_manager.config.extended.group_added_msg)
        return
