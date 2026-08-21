"""handlers 包统一导出

所有事件处理器（命令 / 消息 / 通知）在此收敛，
供 matcher_manager 数据驱动路由表注册使用。
"""

from .add_notices import add_notices
from .chat import entry as chat
from .chat_switch import chat_switch
from .chatobj import chatobj_manage
from .choose_prompt import choose_prompt
from .debug_switchs import debug_switchs
from .del_memory import del_memory
from .insights import insights
from .mcp import mcp_command
from .menus import menu
from .poke_event import poke_event
from .presets import presets
from .prompt import prompt
from .recall import recall
from .sessions import sessions
from .set_preset import set_preset
from .show_abstract import abstract_show

__all__ = [
    "abstract_show",
    "add_notices",
    "chat",
    "chat_switch",
    "chatobj_manage",
    "choose_prompt",
    "debug_switchs",
    "del_memory",
    "insights",
    "mcp_command",
    "menu",
    "poke_event",
    "presets",
    "prompt",
    "recall",
    "sessions",
    "set_preset",
]
