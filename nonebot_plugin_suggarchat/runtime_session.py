"""
会话生命周期管理器

将原 AmritaChatObject._manage_sessions 的逻辑抽离为独立模块。
初始化与执行阶段完全隔离，不再依赖 ChatObject 重写。
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from amrita_core.types import MemoryModel
from amrita_sense.logging import debug_log
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot_plugin_amrita.database import (
    MemorySessions,
    UserDataExecutor,
)
from nonebot_plugin_amrita.memory import (
    CachedUserDataRepository,
    MemorySchema,
)
from nonebot_plugin_orm import get_session
from pydantic import BaseModel, Field

from .config import Config
from .utils.sql import get_uni_user_id


def _is_continue_command(text: str) -> bool:
    """检测用户输入是否意图恢复超时会话。

    支持 "继续"、"继续吧"、"继续聊天"、"接着聊" 等变体，
    使用前缀匹配 + 常见变体关键词列表，排除误匹配。
    """
    text = text.strip()
    return text.startswith("继续") or text.startswith("接着") or text == "续聊"


class SessionTemp(BaseModel):
    """超时会话的临时记录：提示消息ID + 时间戳"""

    message_id: int
    timestamp: datetime = Field(default_factory=datetime.now)


@dataclass
class SessionTempManager:
    """
    全局会话临时记录管理器。

    session_clear_group — 群聊中超时待清理的会话
    session_clear_user  — 私聊中超时待清理的会话
    """

    session_clear_group: dict[str, SessionTemp] = field(default_factory=dict)
    session_clear_user: dict[str, SessionTemp] = field(default_factory=dict)


chat_manager = SessionTempManager()


class SessionManager:
    """
    会话生命周期管理器。

    负责：
      - 会话超时检测与自动归档（存入 MemorySessions 表）
      - 过期归档记录的清理（保留最近 N 条）
      - "继续"功能：超时后通过消息恢复历史上下文
      - 超时提示消息的发送与自动清理

    用法:
        mgr = SessionManager(
            event=event,
            data=memory_data,
            memory=memory_schema,
            matcher=matcher,
            bot=bot,
            config=bot_config,
            session_id=session_id,
        )
        await mgr.manage()


    """

    def __init__(
        self,
        *,
        event: MessageEvent,
        data: MemoryModel,
        memory: MemorySchema,
        matcher: Matcher,
        bot: Bot,
        config: Config,
    ):
        self._event = event
        self._data = data
        self._memory = memory
        self._matcher = matcher
        self._bot = bot
        self._config = config
        self._session_id = get_uni_user_id(event)
        self._repo = CachedUserDataRepository()

    async def manage(self) -> None:
        """
        执行会话管理流程。

        流程顺序（任一环节可能通过 matcher.finish() 提前终止）：

        1. 检查是否存在待处理的超时清理记录
           — 若用户未发"继续"，清除该记录并跳过后续步骤

        2. 检查当前会话是否超时
           — 超时则归档当前数据、清空上下文、发送继续提示

        3. 检查用户是否在超时后发送了"继续"命令
           — 恢复最近一次归档的会话、清理旧提示消息
        """
        cfg = self._config.session
        if not cfg.session_control:
            return

        event = self._event
        data = self._data
        matcher = self._matcher
        bot = self._bot
        session_id = self._session_id
        debug_log("开始管理会话上下文..")

        is_group = isinstance(event, GroupMessageEvent)
        session_clear_map = (
            chat_manager.session_clear_group
            if is_group
            else chat_manager.session_clear_user
        )
        uni_id = get_uni_user_id(event)
        time_now = time.time()

        try:
            pending = session_clear_map.get(session_id)
            if pending is not None:
                debug_log(f"找到会话清除记录: {session_id}")
                if not _is_continue_command(event.message.extract_plain_text()):
                    debug_log("消息中不包含'继续'，清除会话记录")
                    del session_clear_map[session_id]
                    return

            timeout_sec = float(cfg.session_control_time * 60)
            debug_log(f"检查会话超时，当前时间: {time_now}, 数据时间戳: {data.time}")
            if (time_now - data.time) >= timeout_sec:
                debug_log("会话超时，开始创建新会话..")
                async with get_session() as db_session:
                    async with UserDataExecutor(uni_id, db_session) as executor:
                        await executor.add_session(data)

                    await MemorySessions._expire(
                        db_session, uni_id, cfg.session_control_history
                    )
                    await db_session.commit()
                data.messages = []
                timestamp = data.time
                data.time = time_now
                CachedUserDataRepository._cached_memory.pop(uni_id, None)
                self._memory.memory_json = data
                await self._repo.update_memory_data(self._memory)

                within_grace = (time_now - timestamp) <= float(
                    cfg.session_control_time * 60 * 2
                )
                if within_grace and cfg.session_allow_continue:
                    debug_log("发送继续聊天提示")
                    chated: dict[str, Any] = await matcher.send(
                        f'如果想和我继续用之前的上下文聊天，快at我回复✨"继续"✨吧！'
                        f"\n（超过{cfg.session_control_time}分钟没理我我就会被系统抱走存档哦！）"
                    )
                    session_clear_map[session_id] = SessionTemp(
                        message_id=chated["message_id"],
                        timestamp=datetime.now(),
                    )
                    await matcher.finish()

            pending: SessionTemp | None = session_clear_map.get(session_id)
            if pending is not None and _is_continue_command(
                event.message.extract_plain_text()
            ):
                debug_log("检测到'继续'消息，恢复上下文..")

                with contextlib.suppress(Exception):
                    if (
                        time_now - pending.timestamp.timestamp() < 100
                    ):  #  QQ 两分钟撤回窗口期
                        await bot.delete_msg(message_id=pending.message_id)

                session_clear_map.pop(session_id, None)

                sessions = await self._repo.get_sesssions(get_uni_user_id(event))
                data.messages = sessions[-1].data.messages
                last_session = sessions[-1]

                async with UserDataExecutor(uni_id) as executor:
                    await executor.remove_session(last_session.id)

                self._memory.memory_json = data
                await self._repo.update_memory_data(self._memory)
                await matcher.finish("让我们继续聊天吧～")

        finally:
            data.time = time.time()
            debug_log("会话上下文管理完成")
