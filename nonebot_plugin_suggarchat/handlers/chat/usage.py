"""Token 用量统计与持久化（从原 chat.py 抽出）

- usage 缺失时用 tokenizer 估算 prompt/completion tokens
- 汇总后写入全局 InsightsModel 与用户/群元数据
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from amrita_core import UniResponseUsage, debug_log, text_generator
from amrita_core.tokenizer import hybrid_token_count
from amrita_core.utils import gather_usage
from nonebot_plugin_amrita.database import InsightsModel

from ...utils.libchat import add_usage
from ...utils.sql import get_uni_user_id

if TYPE_CHECKING:
    from amrita_core.chatmanager import ChatObject as CoreChatObject
    from nonebot.adapters.onebot.v11 import MessageEvent
    from nonebot_plugin_amrita.memory import CachedUserDataRepository

__all__ = ["record_usage"]


async def _estimate_usage(chat: CoreChatObject) -> UniResponseUsage:
    """响应未携带 usage 时，用 tokenizer 估算 prompt/completion tokens"""
    assert chat._di_working.context_wrap is not None
    response = chat._di_resp.response
    assert response is not None
    resp: str = response.content
    usg_prompt: int = 0
    for i in text_generator(chat._di_working.context_wrap.unwrap(), full_message=True):
        usg_prompt += await asyncio.to_thread(
            hybrid_token_count, i, tokenizer_type="jieba"
        )
    usg_gen = await asyncio.to_thread(hybrid_token_count, resp, tokenizer_type="jieba")
    return UniResponseUsage(
        prompt_tokens=usg_prompt,
        completion_tokens=usg_gen,
        total_tokens=usg_prompt + usg_gen,
    )


async def record_usage(
    chat: CoreChatObject,
    event: MessageEvent,
    cudr: CachedUserDataRepository,
) -> None:
    """统计本次对话 token 用量并持久化到全局洞察与用户/群元数据"""
    if chat._di_resp.response is None:
        return

    insights = await InsightsModel.get()
    debug_log(f"获取洞察数据完成，使用计数: {insights.usage_count}")
    assert chat._di_working.context_wrap is not None

    usg = chat._di_resp.response.usage
    if usg is None:
        usg = await _estimate_usage(chat)

    usage = gather_usage(usg, chat._di_resp.extra_usage)
    add_usage(insights, usage)
    await insights.save()
    debug_log(f"更新全局统计完成，使用计数: {insights.usage_count}")

    ins = await cudr.get_metadata(get_uni_user_id(event))
    for d in (
        (
            ins,
            await cudr.get_metadata(f"user_{event.user_id}"),
        )
        if hasattr(event, "group_id")
        else (ins,)
    ):
        d.called_count
        add_usage(d, usage)
        await cudr.update_metadata(d)
