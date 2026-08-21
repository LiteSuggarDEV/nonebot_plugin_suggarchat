from amrita_sense import logging
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg


async def debug_switchs(
    event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """调试模式开关：on/off/status（显式状态，不再隐式 toggle）"""
    arg = args.extract_plain_text().strip().lower()

    match arg:
        case "on" | "开" | "启用" | "enable":
            logging.debug = True
            await matcher.finish(
                "✅ 已开启调试模式（该模式适用于开发者，请普通用户关闭调试模式）"
            )
        case "off" | "关" | "禁用" | "disable":
            logging.debug = False
            await matcher.finish("✅ 已关闭调试模式")
        case "status" | "状态" | "查看" | "":
            await matcher.finish(
                f"调试模式：{'✅ 开启' if logging.debug else '❌ 关闭'}"
            )
        case _:
            await matcher.finish("用法：/debug on|off|status")
