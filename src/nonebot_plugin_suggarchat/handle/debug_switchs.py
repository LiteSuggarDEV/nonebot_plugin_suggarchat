from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher

from ..chatmanager import chat_manager
from ..config import config_manager


async def debug_switchs(event: MessageEvent, matcher: Matcher):
    """根据用户权限切换调试模式"""
    # 如果配置未启用，跳过处理
    if not config_manager.config.enable:
        matcher.skip()
    # 如果用户不是管理员，直接返回
    if event.user_id not in config_manager.config.admins:
        return
    # 切换调试模式状态并发送提示信息
    if chat_manager.debug:
        chat_manager.debug = False
        await matcher.finish(
            "已关闭调试模式（该模式适用于开发者，请普通用户关闭调试模式）"
        )
    else:
        chat_manager.debug = True
        await matcher.finish(
            "已开启调试模式（该模式适用于开发者，请普通用户关闭调试模式）"
        )
