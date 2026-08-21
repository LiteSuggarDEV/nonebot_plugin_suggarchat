"""/session 域命令：会话管理、元信息、压缩、记忆"""

from __future__ import annotations

import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime

from amrita_core.chatmanager import MemoryLimiter
from amrita_core.types import MemoryModel as AwaredMemory
from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot_plugin_amrita.database import UserDataExecutor
from nonebot_plugin_amrita.memory import CachedUserDataRepository
from nonebot_plugin_orm import get_session

from ..config import config_manager
from ..utils.context import build_train_dict, estimate_tokens
from ..utils.libchat import add_usage
from ..utils.preset import resolve_preset
from ..utils.sql import get_uni_user_id

# 上下文占用低于 MaxTokens 该比例时拒绝压缩
COMPACT_MIN_RATIO = 0.15


# 会话管理


async def _session_list(event: MessageEvent, matcher: Matcher) -> None:
    """显示历史会话列表"""
    repo = CachedUserDataRepository()
    sessions = await repo.get_sesssions(get_uni_user_id(event))
    if not sessions:
        await matcher.finish("没有历史会话")
    msg = "历史会话\n"
    for index, s in enumerate(sessions):
        if s.data.messages:
            abstract = s.data.abstract[:15] or "（无描述）"
            t = datetime.fromtimestamp(s.created_at).strftime("%Y-%m-%d %I:%M:%S %p")
            msg += f"编号：{index}）{abstract}... 时间：{t}\n"
    await matcher.finish(msg)


async def _session_use(event: MessageEvent, matcher: Matcher, index: str) -> None:
    """将当前会话覆盖为指定编号的会话"""
    repo = CachedUserDataRepository()
    try:
        session_index = int(index)
        user_sessions = await repo.get_sesssions(get_uni_user_id(event))
    except ValueError:
        await matcher.finish("请输入正确的编号")
    except Exception as e:
        logger.opt(exception=e, colors=True, raw=True).exception("覆盖记忆文件失败。")
        await matcher.finish("覆盖记忆文件失败，这个对话可能损坏了。")
    if not 0 <= session_index < len(user_sessions):
        await matcher.finish("请输入正确的编号")
    target = user_sessions[session_index]
    try:
        memory_data = await repo.get_memory(get_uni_user_id(event))
        memory_data.memory_json.messages = deepcopy(target.data.messages)
        await repo.update_memory_data(memory_data)
    except Exception as e:
        logger.opt(exception=e, colors=True, raw=True).exception("覆盖记忆文件失败。")
        await matcher.finish("覆盖记忆文件失败，这个对话可能损坏了。")
    await matcher.send("✅ 已完成记忆覆盖。")


async def _session_del(event: MessageEvent, matcher: Matcher, index: str) -> None:
    """删除指定编号的会话"""
    repo = CachedUserDataRepository()
    uni_id = get_uni_user_id(event)
    try:
        session_index = int(index)
        user_sessions = await repo.get_sesssions(uni_id)
    except ValueError:
        await matcher.finish("请输入正确的编号")
    except Exception as e:
        logger.opt(exception=e, colors=True, raw=True).exception(
            "删除指定编号会话失败。"
        )
        await matcher.finish("删除指定编号会话失败。")
    if not 0 <= session_index < len(user_sessions):
        await matcher.finish("请输入正确的编号")
    removed = list(user_sessions).pop(session_index)
    try:
        async with get_session() as session:
            async with UserDataExecutor(uni_id, session) as executor:
                await executor.remove_session(removed.id)
    except Exception as e:
        logger.opt(exception=e, colors=True, raw=True).exception(
            "删除指定编号会话失败。"
        )
        await matcher.finish("删除指定编号会话失败。")
    await matcher.send("✅ 已删除对应的会话。")


async def _session_archive(event: MessageEvent, matcher: Matcher) -> None:
    """归档当前会话"""
    repo = CachedUserDataRepository()
    uni_id = get_uni_user_id(event)
    try:
        memory_data = await repo.get_memory(uni_id)
    except Exception as e:
        logger.opt(exception=e, colors=True, raw=True).exception("归档当前会话失败。")
        await matcher.finish("归档当前会话失败。")
    if not memory_data.memory_json.messages:
        await matcher.finish("当前对话为空！")
    new_session = AwaredMemory(
        messages=deepcopy(memory_data.memory_json.messages),
        abstract=memory_data.memory_json.abstract,
    )
    try:
        async with get_session() as session:
            async with UserDataExecutor(uni_id, session) as executor:
                await executor.add_session(new_session)
        memory_data.memory_json.messages = []
        await repo.update_memory_data(memory_data)
    except Exception as e:
        logger.opt(exception=e, colors=True, raw=True).exception("归档当前会话失败。")
        await matcher.finish("归档当前会话失败。")
    await matcher.finish("✅ 当前会话已归档。")


async def _session_clear(event: MessageEvent, matcher: Matcher) -> None:
    """清空所有历史会话"""
    repo = CachedUserDataRepository()
    uni_id = get_uni_user_id(event)
    user_sessions = await repo.get_sesssions(uni_id)
    if user_sessions:
        async with get_session() as session:
            async with UserDataExecutor(uni_id, session) as executor:
                await executor.remove_session(*[s.id for s in user_sessions])
    await matcher.finish("✅ 会话已清空。")


# 元信息


async def _session_info(event: MessageEvent, matcher: Matcher) -> None:
    """展示当前会话的模型、思考深度与上下文 token 占用"""
    config = config_manager.config
    repo = CachedUserDataRepository()
    memory = await repo.get_memory(get_uni_user_id(event))
    data = memory.memory_json

    preset = await resolve_preset()
    train = build_train_dict(event, memory, config)
    max_tokens = config.core.llm.session_tokens_windows
    total = await asyncio.to_thread(estimate_tokens, train, memory, config)

    roles = Counter(getattr(msg, "role", "?") for msg in data.messages)

    lines = ["📊 当前会话元信息"]
    lines.append(f"模型：{preset.name}（{preset.model}）")
    if preset.thinking_config is not None:
        tc = preset.thinking_config
        enabled = tc.thinking_type == "enabled" or tc.enable_thinking is True
        state = "已启用" if enabled else "已关闭"
        lines.append(f"思考深度：{tc.thinking_effort or '—'}（{state}）")
    lines.append(
        f"上下文：{total} / {max_tokens} tokens"
        + (f"（{total / max_tokens:.1%}）" if max_tokens > 0 else "")
    )
    detail = " ".join(f"{role}:{count}" for role, count in roles.items())
    lines.append(f"消息数：{len(data.messages)} 条（{detail or '空'}）")
    await matcher.send("\n".join(lines))


# 压缩


async def _session_compact(event: MessageEvent, matcher: Matcher, force: bool) -> None:
    """压缩当前会话上下文：将早期消息总结为摘要"""
    config = config_manager.config
    repo = CachedUserDataRepository()
    uni_id = get_uni_user_id(event)
    memory = await repo.get_memory(uni_id)
    data = memory.memory_json
    if not data.messages:
        await matcher.finish("当前会话为空，无需压缩。")

    train = build_train_dict(event, memory, config)
    max_tokens = config.core.llm.session_tokens_windows
    current_tokens = await asyncio.to_thread(estimate_tokens, train, memory, config)

    ratio = current_tokens / max_tokens if max_tokens > 0 else 1.0
    if not force and ratio < COMPACT_MIN_RATIO:
        await matcher.finish(
            f"当前上下文 {current_tokens}/{max_tokens} tokens（{ratio:.1%}），"
            f"未达到 {COMPACT_MIN_RATIO:.0%} 的压缩阈值，暂不需要压缩。"
        )

    work_config = config.core
    llm = work_config.llm
    saved_llm: tuple[bool, int] | None = None
    if force:
        saved_llm = (llm.enable_memory_abstract, llm.memory_length_limit)
        llm.enable_memory_abstract = True
        llm.memory_length_limit = max(
            1,
            int(len(data.messages) * (1 - llm.memory_abstract_proportion)),
        )

    usage = None
    try:
        async with repo.make_lock(uni_id):
            async with MemoryLimiter(
                data, train, config=work_config, preset=await resolve_preset(config.preset)
            ) as lim:
                await lim.run_enforce()
                usage = lim.usage
    except Exception as e:
        logger.opt(exception=e, colors=True, raw=True).exception("压缩会话上下文失败。")
        await matcher.finish("压缩失败，会话已回滚。")
    finally:
        if saved_llm is not None:
            llm.enable_memory_abstract, llm.memory_length_limit = saved_llm

    after_tokens = await asyncio.to_thread(estimate_tokens, train, memory, config)
    await repo.update_memory_data(memory)

    if usage is not None:
        ins = await repo.get_metadata(uni_id)
        add_usage(ins, usage)
        await repo.update_metadata(ins)

    if after_tokens >= current_tokens:
        await matcher.send(
            f"当前上下文未超出限制（{current_tokens}/{max_tokens} tokens），无需压缩。"
        )
    else:
        msg = f"✅ 压缩完成：{current_tokens} -> {after_tokens} tokens"
        if usage is not None:
            msg += (
                f"（摘要消耗 {usage.prompt_tokens + usage.completion_tokens} tokens）"
            )
        await matcher.send(msg)


# 记忆


async def _session_forget(event: MessageEvent, matcher: Matcher) -> None:
    """清空当前记忆"""
    repo = CachedUserDataRepository()
    data = await repo.get_memory(get_uni_user_id(event))
    data.memory_json.messages.clear()
    await repo.update_memory_data(data)
    await matcher.send("上下文已清除")


async def _session_abstract(event: MessageEvent, matcher: Matcher, clear: bool) -> None:
    """查看或清空当前会话摘要"""
    repo = CachedUserDataRepository()
    data = await repo.get_memory(get_uni_user_id(event))
    if clear:
        data.memory_json.abstract = ""
        await repo.update_memory_data(data)
        await matcher.send("已清空对话上下文摘要")
    else:
        await matcher.send(
            f"当前对话上下文摘要：\n{str(data.memory_json.abstract) or '无'}"
        )
    data.clean()  # Ensure the memory is not dirty


# 入口


async def sessions(
    bot: Bot, event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """/session 命令入口（权限由 matcher_manager 统一控制）"""
    arg_list = args.extract_plain_text().strip().split()
    sub = arg_list[0] if arg_list else "info"

    match sub:
        case "info" | "信息" | "元信息":
            await _session_info(event, matcher)
        case "list" | "历史" | "列表":
            await _session_list(event, matcher)
        case "use" | "set" | "覆盖" | "恢复":
            await _session_use(event, matcher, arg_list[1] if len(arg_list) > 1 else "")
        case "del" | "delete" | "删除":
            await _session_del(event, matcher, arg_list[1] if len(arg_list) > 1 else "")
        case "archive" | "归档":
            await _session_archive(event, matcher)
        case "clear" | "清空":
            await _session_clear(event, matcher)
        case "compact" | "压缩":
            force = len(arg_list) > 1 and arg_list[1] in ("force", "-f", "--force")
            await _session_compact(event, matcher, force)
        case "forget" | "失忆" | "清除记忆":
            await _session_forget(event, matcher)
        case "abstract" | "摘要":
            clear = len(arg_list) > 1 and arg_list[1] in ("clear", "clean", "reset")
            await _session_abstract(event, matcher, clear)
        case _:
            await matcher.finish(
                "用法：\n"
                "/session info — 会话元信息（模型/思考/tokens）\n"
                "/session list — 历史会话\n"
                "/session use <编号> — 恢复指定会话\n"
                "/session del <编号> — 删除指定会话\n"
                "/session archive — 归档当前会话\n"
                "/session clear — 清空全部历史\n"
                "/session compact [force] — 压缩上下文\n"
                "/session forget — 清除当前记忆\n"
                "/session abstract [clear] — 查看/清空摘要"
            )
