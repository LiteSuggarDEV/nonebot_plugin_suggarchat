from nonebot import on_command, on_message, on_notice
from nonebot.rule import Rule

from .check_rule import (
    is_bot_admin,
    is_bot_enabled,
    is_group_admin,
    is_group_admin_if_is_in_group,
    should_respond_to_message,
)
from .handle.add_notices import add_notices
from .handle.chat import chat
from .handle.choose_prompt import choose_prompt
from .handle.debug_switchs import debug_switchs
from .handle.del_memory import del_memory
from .handle.disable import disable
from .handle.enable import enable
from .handle.fakepeople_switch import switch
from .handle.menus import menu
from .handle.poke_event import poke_event
from .handle.presets import presets
from .handle.prompt import prompt
from .handle.recall import recall
from .handle.sessions import sessions
from .handle.set_preset import set_preset

on_notice(priority=5, block=False, rule=is_bot_enabled).append_handler(add_notices)
on_notice(priority=5, block=False, rule=is_bot_enabled).append_handler(poke_event)
on_notice(priority=5, rule=is_bot_enabled, block=False).append_handler(recall)

on_message(
    block=False, priority=11, rule=Rule(should_respond_to_message, is_bot_enabled)
).append_handler(chat)

on_command(
    "prompt", priority=10, block=True, rule=Rule(is_group_admin, is_bot_enabled)
).append_handler(prompt)
on_command(
    "presets", priority=10, block=True, rule=Rule(is_bot_admin, is_bot_enabled)
).append_handler(presets)
on_command(
    "set_preset",
    aliases={"设置预设", "设置模型预设"},
    priority=10,
    block=True,
    rule=is_bot_admin,
).append_handler(set_preset)
on_command(
    "debug", priority=10, block=True, rule=Rule(is_bot_admin, is_bot_enabled)
).append_handler(debug_switchs)
on_command(
    "autochat",
    aliases={"fake_people", "假人开关"},
    priority=10,
    block=True,
    rule=Rule(is_group_admin, is_bot_enabled),
).append_handler(switch)
on_command(
    "choose_prompt", priority=10, block=True, rule=Rule(is_bot_enabled, is_bot_admin)
).append_handler(choose_prompt)

on_command(
    "sessions", priority=10, block=True, rule=is_group_admin_if_is_in_group
).append_handler(sessions)
on_command(
    "del_memory",
    aliases={"失忆", "删除记忆", "删除历史消息", "删除回忆"},
    block=True,
    priority=10,
    rule=Rule(is_group_admin_if_is_in_group, is_bot_enabled),
).append_handler(del_memory)
on_command(
    "enable",
    aliases={"启用聊天", "enable_chat"},
    block=True,
    priority=10,
    rule=Rule(is_group_admin, is_bot_enabled),
).append_handler(enable)
on_command(
    "disable",
    aliases={"禁用聊天", "disable_chat"},
    block=True,
    priority=10,
    rule=Rule(is_group_admin, is_bot_enabled),
).append_handler(disable)

on_command(
    "聊天菜单", block=True, aliases={"chat_menu"}, priority=10, rule=is_bot_enabled
).append_handler(menu)
