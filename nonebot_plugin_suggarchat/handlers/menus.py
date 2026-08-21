"""聊天菜单命令"""

from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.matcher import Matcher

from ..config import config_manager
from ..utils.send import send_forward_msg

_MENU_MSG = (
    "—— SuggarChat 菜单 ——\n"
    "📝 直接发送消息与我聊天\n"
    "/prompt — 自定义提示词\n"
    "/choose_prompt — 切换提示词模板\n"
    "/presets — 查看模型列表\n"
    "/set_preset <名> — 切换模型\n"
    "/sessions — 会话管理\n"
    "/del_memory — 清除记忆\n"
    "/show-abstract — 查看摘要\n"
    "/insights — 今日用量\n"
    "/chatobj — 会话状态\n"
    "/mcp — MCP 管理\n"
    "/debug on|off|status — 调试开关\n"
    "/chat on|off — 启用/禁用聊天\n"
    "/chat auto on|off — 自动回复\n"
    "/chat status — 查看状态"
)


async def menu(bot: Bot, event: MessageEvent, matcher: Matcher):
    """处理聊天菜单命令"""
    config = config_manager.config
    msg = _MENU_MSG + (
        f"\n{'群内可以 at 我与我聊天，' if config.function.enable_group_chat else '未启用群内聊天，'}"
        f"{'在私聊可以直接聊天。' if config.function.enable_private_chat else '未启用私聊聊天'}"
        "\nPowered by SuggarChat"
    )
    await send_forward_msg(
        bot, event, "菜单", str(event.self_id), [MessageSegment.text(msg)]
    )
