import random

from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupRecallNoticeEvent
from nonebot.matcher import Matcher

from ..config import config_manager


async def recall(bot: Bot, event: GroupRecallNoticeEvent, matcher: Matcher):
    """处理消息撤回事件"""
    # 随机决定是否响应，降低触发频率
    if random.randint(1, 3) != 2:
        return
    # 检查是否允许在删除自身消息后回复，不允许则返回
    if not config_manager.config.extended.say_after_self_msg_be_deleted:
        return
    if event.user_id == event.self_id:
        if event.operator_id == event.self_id:
            return
        recallmsg = config_manager.config.extended.after_deleted_say_what
        await matcher.send(random.choice(recallmsg))
        return
