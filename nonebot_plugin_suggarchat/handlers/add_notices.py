from nonebot.adapters.onebot.v11.event import GroupIncreaseNoticeEvent
from nonebot.matcher import Matcher

from ..config import config_manager


async def add_notices(event: GroupIncreaseNoticeEvent, matcher: Matcher):
    """处理群聊增加通知事件的异步函数"""
    # 检查配置是否需要在被邀请后发送消息，如果不需要则直接返回
    if not config_manager.config.extended.send_msg_after_be_invited:
        return
    # 如果事件的用户 ID 与机器人自身 ID 相同，表示机器人被邀请加入群聊
    if event.user_id == event.self_id:
        # 发送配置中设置的群聊添加消息
        await matcher.send(config_manager.config.extended.group_added_msg)
        return
