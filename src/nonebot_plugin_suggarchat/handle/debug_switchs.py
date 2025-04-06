# 处理调试模式开关的函数
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher

from ..chatmanager import chat_manager
from ..config import config_manager


async def debug_switchs(event: MessageEvent, matcher: Matcher):
    """根据用户权限开启或关闭调试模式"""
    if not config_manager.config.enable:
        matcher.skip()
    # 如果不是管理员用户，直接返回
    if event.user_id not in config_manager.config.admins:
        return
    # 根据当前调试模式状态，开启或关闭调试模式，并发送通知
    if chat_manager.debug:
        chat_manager.debug = False
        await matcher.finish(
            "已关闭调试模式（该模式适用于开发者，如果你作为普通用户使用，请关闭调试模式）"
        )
    else:
        chat_manager.debug = True
        await matcher.finish(
            "已开启调试模式（该模式适用于开发者，如果你作为普通用户使用，请关闭调试模式）"
        )
