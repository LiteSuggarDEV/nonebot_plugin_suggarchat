"""聊天处理器入口（编排）

将原 chat.py 的上帝文件拆分为子包：
- message.py   消息合成/格式化/引用/角色/多模态
- strategy.py  Agent 策略选择与 workflow 装配
- lock.py      pending_mode 锁策略（State 模式）
- streaming.py ChatStreamSender 生命周期与长任务监控
- usage.py     Token 用量统计与持久化

本模块仅保留 entry() 编排主函数。
"""

from __future__ import annotations

from asyncio import CancelledError

from amrita_core import debug_log, logger
from amrita_core.base.backend import BackendSlots
from amrita_core.chatmanager import ChatObject as CoreChatObject
from amrita_core.chatmanager.chat_object import DatabackendOptions
from amrita_core.types import USER_INPUT, Content, Message
from amrita_sense.hook.exception import MatcherException as ChatException
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, MessageEvent
from nonebot.exception import MatcherException, NoneBotException, ProcessException
from nonebot.matcher import Matcher
from nonebot_plugin_amrita.memory import CachedUserDataRepository, MemorySchema

from ...backends import ChatMemoryBackend, NoopAbilityBackend
from ...config import config_manager
from ...runtime import (
    AMRITA_CTX_KEY,
    AmritaBotContext,
    bot_chat_manager,
    pending_chatobj,
)
from ...runtime_session import SessionManager
from ...utils.context import build_train_dict
from ...utils.functions import get_friend_name, synthesize_message
from ...utils.lock import get_group_lock, get_private_lock
from ...utils.preset import resolve_preset
from ...utils.sql import get_uni_user_id
from .lock import get_pending_mode_strategy
from .message import (
    get_reply_pics,
    get_user_role,
    handle_reply,
    synthesize_message_to_msg,
)
from .strategy import build_workflow, select_agent_strategy
from .streaming import StreamSession
from .usage import record_usage

__all__ = ["entry"]

command_prefix = get_driver().config.command_start or "/"


async def entry(event: MessageEvent, matcher: Matcher, bot: Bot):
    """
    聊天处理器入口函数。

    新版流程（初始化与执行完全隔离）：
      1. 会话超时检测与归档（SessionManager）
      2. 加载 memory、合成消息、构建 prompt
      3. 创建 CoreChatObject，通过 hook_kwargs 传递上下文
      4. chat.begin() -> lock -> await chat
      5. 后处理：usage 统计、memory 持久化
    """
    if any(
        event.message.extract_plain_text().strip().startswith(prefix)
        for prefix in command_prefix
        if prefix.strip()
    ):
        matcher.skip()
    session_id = get_uni_user_id(event)
    config = config_manager.config
    cudr = CachedUserDataRepository()

    #  阶段 1：加载 memory 与会话管理
    is_group: bool = isinstance(event, GroupMessageEvent)
    memory: MemorySchema = await cudr.get_memory(
        get_uni_user_id(event),
    )
    data = memory.memory_json

    # 清理异常 message content（仅 Message 需要；ToolResult.content 为 str 无需处理）
    for mem in data.messages:
        if not isinstance(mem, Message):
            continue
        if mem.content is None or isinstance(mem.content, str):
            continue
        mem.content = [i for i in mem.content if isinstance(i, Content)]

    # 会话超时 / 继续恢复
    await SessionManager(
        event=event,
        data=data,
        memory=memory,
        matcher=matcher,
        bot=bot,
        config=config,
    ).manage()
    # manage() 内部可能调用 matcher.finish() 抛出 FinishedException

    #  阶段 2：合成消息
    content: str = await synthesize_message(event.get_message(), bot)
    debug_log(f"合成消息完成: {content}")

    if content.strip() == "":
        content = ""
    if event.reply:
        group_id = event.group_id if is_group else None
        debug_log("处理引用消息..")
        content = await handle_reply(event.reply, bot, group_id, content)

    reply_pics = get_reply_pics(event)
    debug_log(f"获取引用图片完成，共 {len(reply_pics)} 张")

    if is_group:
        debug_log("处理群聊消息")
        user_name = (
            (
                await bot.get_group_member_info(
                    group_id=event.group_id, user_id=event.user_id
                )
            )["nickname"]
            if not config.function.use_user_nickname
            else event.sender.nickname
        )
    else:
        debug_log("处理私聊消息")
        user_name = await get_friend_name(event.user_id, bot=bot)
    role = await get_user_role(bot, event.group_id, event.user_id) if is_group else ""
    final_content: USER_INPUT = await synthesize_message_to_msg(
        event, role, str(user_name), str(event.user_id), content
    )
    if isinstance(final_content, list):
        final_content.extend(reply_pics)

    #  阶段 3：构建策略与 prompt
    strategy = select_agent_strategy(config.llm.agent_strategy)

    # 构建定制化的 system prompt（与 /compact、/session info 共用同一构建逻辑）
    train_dict = build_train_dict(event, memory, config)

    #  阶段 4：创建 ChatObject
    ctx: AmritaBotContext = {
        "matcher": matcher,
        "bot": bot,
        "event": event,
        "bot_config": config_manager.config,
    }
    chat: CoreChatObject = CoreChatObject(
        train=train_dict,
        user_input=final_content,
        session_id=session_id,
        preset=await resolve_preset(),
        hook_args=(event, matcher, bot),
        hook_kwargs={AMRITA_CTX_KEY: ctx},
        exception_ignored=(ProcessException, MatcherException),
        agent_strategy=strategy,
        workflow=build_workflow(config.llm.agent_workflow),
        chat_man=bot_chat_manager,
        backend=BackendSlots(
            NoopAbilityBackend(),
            ChatMemoryBackend(memory),
        ),
        backend_options=DatabackendOptions(
            skip_mcp_fetch=True,
            skip_tools_fetch=True,
        ),
    )

    #  阶段 5：设置回调并启动
    stream = StreamSession(
        matcher,
        bot,
        event,
        config,
        chat,
        notify_sec=config.session.session_long_running_notify_seconds,
        is_group=is_group,
    )
    lock = (
        get_group_lock(event.group_id) if is_group else get_private_lock(event.user_id)
    )

    # 按 chat_pending_mode 处理锁占用场景（single / single_with_report / queue）。
    # 返回 True 表示已停止本次流程。
    if await get_pending_mode_strategy(
        config.function.chat_pending_mode
    ).handle_locked(
        lock=lock,
        matcher=matcher,
        event=event,
        session_id=session_id,
    ):
        return

    try:
        pending_chatobj[session_id].append(chat)
        try:
            async with lock:
                pending_chatobj[session_id].remove(chat)
                debug_log("继续运行...")

                #  私聊模式后台超时监控：若 Agent 工作时间超过阈值仍未返回，
                #  发送提示告知用户如何终止任务
                stream.start_monitor()
                try:
                    async with chat.begin():
                        await chat
                finally:
                    await stream.stop_monitor()

                stream.mark_received()
                await stream.send_final()
        finally:
            # 兜底：异常时清理 pending
            if chat in pending_chatobj[session_id]:
                pending_chatobj[session_id].remove(chat)

    except BaseException as e:
        if isinstance(e, (NoneBotException, ChatException)):
            raise

        if isinstance(e, CancelledError):
            return

        await matcher.send("出错了稍后试试吧（错误已反馈）")
        logger.opt(exception=e, colors=True, raw=True).exception(
            "程序发生了未捕获的异常"
        )
    finally:
        await record_usage(chat, event, cudr)
