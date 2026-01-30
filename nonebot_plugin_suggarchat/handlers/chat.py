"""聊天处理器模块"""

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import (
    Bot,
)
from nonebot.adapters.onebot.v11.event import (
    MessageEvent,
)
from nonebot.matcher import Matcher

from ..chatmanager import ChatObject

command_prefix = get_driver().config.command_start or "/"


async def entry(event: MessageEvent, matcher: Matcher, bot: Bot):
    """聊天处理器入口函数

    该函数作为消息事件的入口点，处理命令前缀检查并启动聊天对象。

    Args:
        event: 消息事件
        matcher: 匹配器
        bot: Bot实例

    Returns:
        聊天处理结果
    """
    if any(
        event.message.extract_plain_text().strip().startswith(prefix)
        for prefix in command_prefix
        if prefix.strip()
    ):
        matcher.skip()
    return await (ChatObject().caller())(event, matcher, bot)
