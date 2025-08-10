from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher

from ..chatmanager import chat_manager


async def debug_switchs(event: MessageEvent, matcher: Matcher):
    """根据用户权限切换调试模式"""

    # 切换调试模式状态并发送提示信息
    if chat_manager.debug:
        chat_manager.debug = False
        await matcher.finish("已关闭调试模式")
    else:
        chat_manager.debug = True
        await matcher.finish(
            "已开启调试模式（该模式适用于开发者，请普通用户关闭调试模式）"
        )
