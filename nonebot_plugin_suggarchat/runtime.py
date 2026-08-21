"""
Runtime 基础设施

提供 Bot 级别的 ChatManager 实例和跨 handler 共享的类型定义。
会话管理逻辑已移至 runtime_session.py。
"""

from __future__ import annotations

from collections import defaultdict
from typing import TypedDict

from amrita_core import ChatObject
from amrita_core.chatmanager import ChatManager
from amrita_core.chatmanager import ChatObject as CoreChatObject
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher

from .config import Config

# hook_kwargs 中存放上下文的键
AMRITA_CTX_KEY = "amrita"


class AmritaBotContext(TypedDict):
    """跨 handler 共享的上下文，消息体走 memory.memory_json"""

    matcher: Matcher
    bot: Bot
    event: MessageEvent
    bot_config: Config


def try_get_amrita_ctx(obj: CoreChatObject) -> AmritaBotContext | None:
    """读取上下文，没有则 None"""
    return obj._hook_kwargs.get(AMRITA_CTX_KEY)


def get_amrita_ctx(obj: CoreChatObject) -> AmritaBotContext:
    """读取上下文，没有则报错"""
    ctx = try_get_amrita_ctx(obj)
    if ctx is None:
        raise RuntimeError("缺少 AmritaBotContext")
    return ctx


bot_chat_manager = ChatManager()

pending_chatobj: defaultdict[str, list[ChatObject]] = defaultdict(list)
