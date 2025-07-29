from nonebot.matcher import Matcher

from .. import config
from ..chatmanager import chat_manager
from ..config import config_manager


async def menu(matcher: Matcher):
    """处理聊天菜单命令"""

    # 初始化消息内容为默认菜单消息
    msg = chat_manager.menu_msg

    # 遍历自定义菜单项，添加到消息内容
    for menus in chat_manager.custom_menu:
        msg += f"\n{menus['cmd']} {menus['describe']}"

    # 根据配置添加群聊或私聊的提示信息
    msg += f"\n{'群内可以at我与我聊天，' if config_manager.config.function.enable_group_chat else '未启用群内聊天，'}{'在私聊可以直接聊天。' if config_manager.config.function.enable_private_chat else '未启用私聊聊天'}\nPowered by SuggarChat V{config.__kernel_version__}"

    # 发送最终消息内容
    await matcher.send(msg)
