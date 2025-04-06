import random

from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11.event import GroupRecallNoticeEvent
from nonebot.matcher import Matcher

from ..config import config_manager


async def recall(bot: Bot, event: GroupRecallNoticeEvent, matcher: Matcher):
    """处理消息撤回通知事件"""

    # 检查是否启用了插件功能，未启用则跳过后续处理
    if not config_manager.config.enable:
        matcher.skip()
    # 通过随机数决定是否响应，增加趣味性和减少响应频率
    if random.randint(1, 3) != 2:
        return
    # 检查配置中是否允许在删除自己的消息后发言，不允许则直接返回
    if not config_manager.config.say_after_self_msg_be_deleted:
        return
    # 判断事件是否为机器人自己删除了自己的消息
    if event.user_id == event.self_id:
        # 如果是机器人自己删除了自己的消息，并且操作者也是机器人自己，则不进行回复
        if event.operator_id == event.self_id:
            return
        # 从配置中获取删除消息后可能的回复内容
        recallmsg = config_manager.config.after_deleted_say_what
        # 从预设的回复内容中随机选择一条发送
        await matcher.send(random.choice(recallmsg))
        return
