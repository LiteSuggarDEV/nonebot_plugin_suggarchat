"""聊天插件匹配器管理模块

该模块负责管理聊天插件中的所有事件匹配器，包括消息、命令和通知事件的处理。

所有匹配器以数据驱动方式声明在 MATCHERS 路由表中，
由 _register 统一按规格注册，避免重复的注册样板代码。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from nonebot import MatcherGroup
from nonebot.permission import Permission
from nonebot.rule import Rule
from nonebot.typing import T_PermissionChecker

from .check_rule import (
    is_bot_admin,
    is_bot_enabled,
    is_bot_globally_enabled,
    is_group_admin,
    is_group_admin_if_is_in_group,
    should_respond_with_usage_check,
)
from .handlers import (
    abstract_show,
    add_notices,
    chat,
    chat_switch,
    chatobj_manage,
    choose_prompt,
    debug_switchs,
    del_memory,
    insights,
    mcp_command,
    menu,
    poke_event,
    presets,
    prompt,
    recall,
    sessions,
    set_preset,
)

# 创建基础匹配器组，所有匹配器都需满足is_bot_enabled规则
base_matcher = MatcherGroup(rule=is_bot_enabled)

# 聊天开关匹配器组：仅检查全局开关与功能开关，不受每群 enable 标记影响，
# 避免 /chat off 关闭群聊后 is_bot_enabled 失效，导致无法再次执行 /chat on
chat_switch_matcher = MatcherGroup(rule=is_bot_globally_enabled)


@dataclass(frozen=True)
class MatcherSpec:
    """匹配器注册规格（数据驱动路由表条目）

    字段为 None / False 时不传入 NoneBot，使用框架默认值。
    """

    handler: Callable[..., Any]
    kind: Literal["command", "message", "notice"] = "command"
    group: MatcherGroup | None = None
    # command 专用
    command: str | None = None
    aliases: set[str] | None = None
    force_whitespace: bool | None = None
    # 通用
    priority: int | None = None
    block: bool | None = None
    permission: Permission | T_PermissionChecker | None = None
    rule: Rule | None = None


MATCHERS: list[MatcherSpec] = [
    # ---- 通知事件 ----
    MatcherSpec(
        kind="notice",
        handler=add_notices,
        priority=5,
        block=False,
    ),
    MatcherSpec(
        kind="notice",
        handler=poke_event,
        priority=5,
        block=False,
    ),
    MatcherSpec(
        kind="notice",
        handler=recall,
        priority=5,
        block=False,
    ),
    # ---- 消息事件：处理聊天消息 ----
    MatcherSpec(
        kind="message",
        handler=chat,
        block=False,
        priority=11,
        rule=Rule(should_respond_with_usage_check, is_bot_enabled),
    ),
    # ---- 简易菜单：展示聊天功能 ----
    MatcherSpec(
        command="menu",
        aliases={"菜单"},
        priority=10,
        block=True,
        handler=menu,
    ),
    # ---- 摘要 ----
    MatcherSpec(
        command="show-abstract",
        aliases={"abstract"},
        handler=abstract_show,
    ),
    # ---- 提示词域 ----
    MatcherSpec(
        command="prompt",
        priority=10,
        block=True,
        permission=Permission(is_group_admin_if_is_in_group),
        handler=prompt,
    ),
    MatcherSpec(
        command="choose_prompt",
        priority=10,
        block=True,
        permission=is_bot_admin,
        handler=choose_prompt,
    ),
    MatcherSpec(
        command="presets",
        priority=10,
        block=True,
        permission=is_bot_admin,
        handler=presets,
    ),
    MatcherSpec(
        command="set_preset",
        aliases={"设置预设", "设置模型预设"},
        priority=10,
        block=True,
        permission=is_bot_admin,
        handler=set_preset,
    ),
    # ---- 会话域 ----
    MatcherSpec(
        command="sessions",
        priority=10,
        block=True,
        permission=is_bot_admin,
        handler=sessions,
    ),
    MatcherSpec(
        command="del_memory",
        aliases={"失忆", "删除记忆", "删除历史消息", "删除回忆"},
        block=True,
        priority=10,
        handler=del_memory,
    ),
    MatcherSpec(
        command="chatobj",
        aliases={"chat_obj"},
        permission=is_group_admin_if_is_in_group,
        handler=chatobj_manage,
    ),
    # ---- 用量统计 ----
    MatcherSpec(
        command="insights",
        aliases={"今日用量"},
        block=True,
        priority=10,
        handler=insights,
    ),
    # ---- MCP 管理 ----
    MatcherSpec(
        command="mcp",
        aliases={"MCP管理"},
        permission=is_bot_admin,
        handler=mcp_command,
    ),
    # ---- 调试 ----
    MatcherSpec(
        command="debug",
        priority=10,
        block=True,
        permission=is_bot_admin,
        handler=debug_switchs,
    ),
    # ---- 聊天开关域 ----
    MatcherSpec(
        command="chat",
        aliases={"聊天开关", "chat_switch"},
        priority=10,
        block=True,
        permission=is_group_admin,
        group=chat_switch_matcher,
        handler=chat_switch,
    ),
]


def _register(spec: MatcherSpec) -> None:
    """按规格注册单个匹配器"""
    group = spec.group or base_matcher
    kwargs: dict[str, Any] = {}
    if spec.priority is not None:
        kwargs["priority"] = spec.priority
    if spec.block is not None:
        kwargs["block"] = spec.block
    if spec.permission is not None:
        kwargs["permission"] = spec.permission

    if spec.kind == "notice":
        matcher = group.on_notice(**kwargs)
    elif spec.kind == "message":
        if spec.rule is not None:
            kwargs["rule"] = spec.rule
        matcher = group.on_message(**kwargs)
    else:
        assert spec.command is not None, "command 类匹配器必须提供 command"
        if spec.aliases is not None:
            kwargs["aliases"] = spec.aliases
        # 仅当显式指定时才传入，避免 False 覆盖 NoneBot 默认的 None
        # （NoneBot 中 force_whitespace=False 表示命令后必须无空白，
        #  会导致 `/chat on` 这类带空格参数的命令静默失配）
        if spec.force_whitespace is not None:
            kwargs["force_whitespace"] = spec.force_whitespace
        matcher = group.on_command(spec.command, **kwargs)
    matcher.append_handler(spec.handler)


for _spec in MATCHERS:
    _register(_spec)
