"""聊天插件匹配器管理模块

该模块负责管理聊天插件中的所有事件匹配器，包括消息、命令和通知事件的处理。
"""

from nonebot import MatcherGroup, on_command
from nonebot.permission import Permission
from nonebot.rule import Rule

from .check_rule import (
    is_bot_admin,
    is_bot_enabled,
    is_group_admin,
    is_group_admin_if_is_in_group,
    should_respond_with_usage_check,
)
from .handlers.add_notices import add_notices
from .handlers.chat import entry as chat
from .handlers.chatobj import chatobj_manage
from .handlers.choose_prompt import choose_prompt
from .handlers.debug_switchs import debug_switchs
from .handlers.del_memory import del_memory
from .handlers.disable import disable
from .handlers.enable import enable
from .handlers.fakepeople_switch import switch
from .handlers.insights import insights
from .handlers.mcp import (
    mcp_command,
)
from .handlers.poke_event import poke_event
from .handlers.preset_test import t_preset
from .handlers.presets import presets
from .handlers.prompt import prompt
from .handlers.recall import recall
from .handlers.sessions import sessions
from .handlers.set_preset import set_preset
from .handlers.show_abstract import abstract_show

# 创建基础匹配器组，所有匹配器都需满足is_bot_enabled规则
base_matcher = MatcherGroup(rule=is_bot_enabled)

# 添加通知事件处理器
base_matcher.on_notice(
    priority=5,
    block=False,
).append_handler(add_notices)

base_matcher.on_notice(
    priority=5,
    block=False,
).append_handler(poke_event)

base_matcher.on_notice(
    priority=5,
    block=False,
).append_handler(recall)

# 添加消息事件处理器，处理聊天消息
base_matcher.on_message(
    block=False,
    priority=11,
    rule=Rule(should_respond_with_usage_check, is_bot_enabled),
).append_handler(chat)

base_matcher.on_command(
    "show-abstract",
    {"abstract"},
).append_handler(abstract_show)
# 添加各种命令处理器
base_matcher.on_command(
    "prompt",
    priority=10,
    block=True,
    permission=Permission(is_group_admin_if_is_in_group),
).append_handler(prompt)

base_matcher.on_command(
    "presets",
    priority=10,
    block=True,
    permission=is_bot_admin,
).append_handler(presets)

base_matcher.on_command(
    "set_preset",
    aliases={"设置预设", "设置模型预设"},
    priority=10,
    block=True,
    permission=is_bot_admin,
).append_handler(set_preset)

base_matcher.on_command(
    "debug",
    priority=10,
    block=True,
    permission=is_bot_admin,
).append_handler(debug_switchs)

base_matcher.on_command(
    "autochat",
    aliases={"自动回复", "autoreply"},
    priority=10,
    block=True,
    permission=is_group_admin,
).append_handler(switch)

base_matcher.on_command(
    "choose_prompt",
    priority=10,
    block=True,
    permission=is_bot_admin,
).append_handler(choose_prompt)

base_matcher.on_command(
    "sessions",
    priority=10,
    block=True,
    permission=is_bot_admin,
).append_handler(sessions)

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
    permission=is_group_admin,
).append_handler(enable)

on_command(
    "disable",
    aliases={"禁用聊天", "disable_chat"},
    block=True,
    priority=10,
    permission=is_group_admin,
).append_handler(disable)

base_matcher.on_command(
    "insights",
    aliases={"今日用量"},
    block=True,
    priority=10,
).append_handler(insights)

base_matcher.on_command(
    "test_preset",
    aliases={"测试预设"},
    block=True,
    priority=10,
    permission=is_bot_admin,
).append_handler(t_preset)

base_matcher.on_command(
    "mcp",
    aliases={"MCP管理"},
    permission=is_bot_admin,
).append_handler(mcp_command)

base_matcher.on_command(
    "chatobj",
    aliases={"chat_obj"},
    permission=is_group_admin_if_is_in_group,
).append_handler(chatobj_manage)
