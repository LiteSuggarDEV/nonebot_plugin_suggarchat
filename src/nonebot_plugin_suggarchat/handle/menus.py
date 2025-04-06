# 当有消息撤回时触发处理函数
# 处理菜单命令的函数
from nonebot.matcher import Matcher

from ..chatmanager import chat_manager
from ..config import config_manager


async def menu(matcher: Matcher):
    """处理聊天菜单命令"""
    if not config_manager.config.enable:
        matcher.skip()

    # 初始化消息内容为默认菜单消息
    msg = chat_manager.menu_msg

    # 遍历自定义菜单项，添加到消息内容中
    for menus in chat_manager.custom_menu:
        msg += f"\n{menus['cmd']} {menus['describe']}"

    # 根据配置信息，添加群聊或私聊聊天可用性的提示信息
    msg += f"\n{'群内可以at我与我聊天，' if config_manager.config.enable_group_chat else '未启用群内聊天，'}{'在私聊可以直接聊天。' if config_manager.config.enable_group_chat else '未启用私聊聊天'}\nPowered by Suggar chat plugin"

    # 发送最终的消息内容
    await matcher.send(msg)
