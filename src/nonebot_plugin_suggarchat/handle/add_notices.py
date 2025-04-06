# 当有人加入群聊时触发的事件处理函数
from nonebot.adapters.onebot.v11.event import GroupIncreaseNoticeEvent
from nonebot.matcher import Matcher

from ..config import config_manager


async def add_notices(event: GroupIncreaseNoticeEvent, matcher: Matcher):
    """处理群聊增加通知事件的异步函数"""
    if not config_manager.config.enable:
        matcher.skip()
    # 检查配置，如果不发送被邀请后的消息，则直接返回
    if not config_manager.config.send_msg_after_be_invited:
        return
    # 如果事件的用户ID与机器人自身ID相同，表示机器人被邀请加入群聊
    if event.user_id == event.self_id:
        # 发送配置中的群聊添加消息
        await matcher.send(config_manager.config.group_added_msg)
        return
