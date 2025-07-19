from collections.abc import Callable, Coroutine
from typing import Any

import nonebot
import openai
from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
)
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from ..chatmanager import chat_manager
from ..config import Config, config_manager
from .admin import send_to_admin_as_error
from .functions import remove_think_tag


async def get_chat(
    messages: list,
    bot: Bot | None = None,
    tokens: int = 0,
) -> str:
    """获取聊天响应"""
    # 获取最大token数量
    max_tokens = config_manager.config.max_tokens
    func = openai_get_chat
    # 根据预设选择API密钥和基础URL
    preset = await config_manager.get_preset(
        config_manager.config.preset, fix=True, cache=False
    )
    is_thought_chain_model = preset.thought_chain_model

    # 检查协议适配器
    if preset.protocol == "__main__":
        func = openai_get_chat
    elif preset.protocol not in protocols_adapters:
        raise ValueError(f"协议 {preset.protocol} 的适配器未找到!")
    else:
        func = protocols_adapters[preset.protocol]
    # 记录日志
    logger.debug(f"开始获取 {preset.model} 的对话")
    logger.debug(f"预设：{config_manager.config.preset}")
    logger.debug(f"密钥：{preset.api_key[:7]}...")
    logger.debug(f"协议：{preset.protocol}")
    logger.debug(f"API地址：{preset.base_url}")
    logger.debug(f"当前对话Tokens:{tokens}")

    nb_bot: Bot = bot if bot else nonebot.get_bot()  # type: ignore
    # 此处获取的Bot一定是onebot适配器的Bot.

    # 调用适配器获取聊天响应
    response = await func(
        preset.base_url,
        preset.model,
        preset.api_key,
        messages,
        max_tokens,
        config_manager.config,
        nb_bot,  # type: ignore
    )
    if chat_manager.debug:
        logger.debug(response)
    return remove_think_tag(response) if is_thought_chain_model else response


async def openai_get_chat(
    base_url: str,
    model: str,
    key: str,
    messages: list,
    max_tokens: int,
    config: Config,
    bot: Bot,
) -> str:
    """核心聊天响应获取函数"""
    # 创建OpenAI客户端
    client = openai.AsyncOpenAI(
        base_url=base_url, api_key=key, timeout=config.llm_timeout
    )
    completion: ChatCompletion | openai.AsyncStream[ChatCompletionChunk] | None = None
    # 尝试获取聊天响应，最多重试3次
    for index, i in enumerate(range(3)):
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                stream=config.stream,
            )
            break
        except Exception as e:
            logger.error(f"发生错误: {e}")
            logger.info(f"第 {i + 1} 次重试")
            if index == 2:
                await send_to_admin_as_error(
                    f"请检查API Key和API base_url！获取对话时发生错误: {e}", bot
                )
                raise e
            continue

    response: str = ""
    # 处理流式响应
    if config.stream and isinstance(completion, openai.AsyncStream):
        async for chunk in completion:
            try:
                if chunk.choices[0].delta.content is not None:
                    response += chunk.choices[0].delta.content
                    if chat_manager.debug:
                        logger.debug(chunk.choices[0].delta.content)
            except IndexError:
                break
    else:
        if chat_manager.debug:
            logger.debug(response)
        if isinstance(completion, ChatCompletion):
            response = (
                completion.choices[0].message.content
                if completion.choices[0].message.content is not None
                else ""
            )
        else:
            raise RuntimeError("收到意外的响应类型")
    return response if response is not None else ""


# 协议适配器映射
protocols_adapters: dict[
    str, Callable[[str, str, str, list, int, Config, Bot], Coroutine[Any, Any, str]]
] = {"openai-builtin": openai_get_chat}
