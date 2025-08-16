from nonebot import MatcherGroup, on_command
from nonebot.rule import Rule

from .check_rule import (
    is_bot_admin,
    is_bot_enabled,
    should_respond_to_message,
)
from .handlers.add_notices import add_notices
from .handlers.chat import chat
from .handlers.choose_prompt import choose_prompt
from .handlers.debug_switchs import debug_switchs
from .handlers.del_memory import del_memory
from .handlers.disable import disable
from .handlers.enable import enable
from .handlers.fakepeople_switch import switch
from .handlers.menus import menu
from .handlers.poke_event import poke_event
from .handlers.presets import presets
from .handlers.prompt import prompt
from .handlers.recall import recall
from .handlers.sessions import sessions
from .handlers.set_preset import set_preset

base_matcher = MatcherGroup(rule=is_bot_enabled)

base_matcher.on_notice(
    priority=5,
    block=False,
).append_handler(add_notices)
base_matcher.on_notice(
    priority=5,
    block=False,
).append_handler(poke_event)
base_matcher.on_notice(priority=5, block=False).append_handler(recall)

base_matcher.on_message(
    block=False, priority=11, rule=Rule(should_respond_to_message)
).append_handler(chat)

base_matcher.on_command(
    "prompt",
    priority=10,
    block=True,
).append_handler(prompt)
base_matcher.on_command(
    "presets", priority=10, block=True, rule=Rule(is_bot_admin)
).append_handler(presets)
base_matcher.on_command(
    "set_preset",
    aliases={"设置预设", "设置模型预设"},
    priority=10,
    block=True,
    rule=is_bot_admin,
).append_handler(set_preset)
base_matcher.on_command(
    "debug", priority=10, block=True, rule=Rule(is_bot_admin)
).append_handler(debug_switchs)
base_matcher.on_command(
    "autochat",
    aliases={"自动回复", "autoreply"},
    priority=10,
    block=True,
).append_handler(switch)
base_matcher.on_command(
    "choose_prompt", priority=10, block=True, rule=Rule(is_bot_admin)
).append_handler(choose_prompt)

base_matcher.on_command("sessions", priority=10, block=True).append_handler(sessions)
base_matcher.on_command(
    "del_memory",
    aliases={"失忆", "删除记忆", "删除历史消息", "删除回忆"},
    block=True,
    priority=10,
).append_handler(del_memory)
on_command(
    "enable",
    aliases={"启用聊天", "enable_chat"},
    block=True,
    priority=10,
).append_handler(enable)
on_command(
    "disable",
    aliases={"禁用聊天", "disable_chat"},
    block=True,
    priority=10,
).append_handler(disable)

base_matcher.on_command(
    "聊天菜单",
    block=True,
    aliases={"chat_menu"},
    priority=10,
).append_handler(menu)
