"""流式发送生命周期与长任务监控（从原 chat.py 抽出）"""

from __future__ import annotations

import asyncio
import contextlib
from asyncio import CancelledError
from typing import TYPE_CHECKING

from ...utils.stream_sender import ChatStreamSender, NoMessageSendError

if TYPE_CHECKING:
    from amrita_core.chatmanager import ChatObject as CoreChatObject
    from nonebot.adapters.onebot.v11 import Bot, MessageEvent
    from nonebot.matcher import Matcher

    from ...config import Config

__all__ = ["LongRunningMonitor", "StreamSession"]


class LongRunningMonitor:
    """私聊长任务监控：Agent 工作超过阈值仍未返回时发送提示

    用法:
        monitor = LongRunningMonitor(matcher, notify_sec)
        monitor.start()          # 开始计时
        ...
        monitor.mark_received()  # 收到响应后置位，阻止后续通知
        await monitor.stop()     # 取消未完成的任务
    """

    def __init__(self, matcher: Matcher, notify_sec: int):
        self._matcher = matcher
        self._notify_sec = notify_sec
        self._response_received = False
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return self._notify_sec > 0

    def start(self) -> None:
        """启动监控任务（notify_sec <= 0 时为空操作）"""
        if not self.enabled:
            return

        async def _notify_long_running() -> None:
            await asyncio.sleep(self._notify_sec)
            if not self._response_received:
                await self._matcher.send(
                    "💡Agent已工作了一会儿，但还是没有给出答案，"
                    "使用/chatobj kill终止当前任务。"
                )

        self._task = asyncio.create_task(_notify_long_running())

    def mark_received(self) -> None:
        """标记已收到响应，阻止后续通知"""
        self._response_received = True

    async def stop(self) -> None:
        """取消未完成的监控任务"""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(CancelledError):
                await self._task


class StreamSession:
    """ChatStreamSender 生命周期管理 + 长任务监控

    封装原 chat.py 中的流式回调挂载、私聊超时监控与最终响应发送，
    使 entry() 只关心编排。
    """

    def __init__(
        self,
        matcher: Matcher,
        bot: Bot,
        event: MessageEvent,
        config: Config,
        chat: CoreChatObject,
        *,
        notify_sec: int,
        is_group: bool,
    ):
        self._chat = chat
        self._sender = ChatStreamSender(matcher, bot, event, config, chat)
        chat.io_stream.set_callback_func(self._sender.handle)
        self._monitor = (
            LongRunningMonitor(matcher, notify_sec)
            if not is_group and notify_sec > 0
            else None
        )

    def start_monitor(self) -> None:
        """启动长任务监控（仅私聊且配置阈值 > 0 时生效）"""
        if self._monitor:
            self._monitor.start()

    async def stop_monitor(self) -> None:
        if self._monitor:
            await self._monitor.stop()

    def mark_received(self) -> None:
        if self._monitor:
            self._monitor.mark_received()

    async def send_final(self) -> None:
        """发送最终响应；钩子可能抛出 NoMessageSendError 静默拦截"""
        if self._chat._di_resp.response is not None:
            with contextlib.suppress(NoMessageSendError):
                await self._sender.send_final(self._chat._di_resp.response.content)
