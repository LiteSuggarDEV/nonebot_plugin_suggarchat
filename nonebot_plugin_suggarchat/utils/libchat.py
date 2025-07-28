from collections.abc import Callable, Coroutine
from copy import deepcopy
from typing import Any

import nonebot
import openai
from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
)
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_tool_choice_option_param import (
    ChatCompletionToolChoiceOptionParam,
)

from ..chatmanager import chat_manager
from ..config import Config, config_manager
from .admin import send_to_admin_as_error
from .functions import remove_think_tag


async def tools_caller(
    messages: list,
    tools: list,
    tool_choice: ChatCompletionToolChoiceOptionParam | None = None,
) -> ChatCompletionMessage:
    if not tool_choice:
        tool_choice = (
            "required"
            if (
                config_manager.config.llm_config.tools.require_tools and len(tools) > 1
            )  # 排除默认工具
            else "auto"
        )
    config = config_manager.config
    preset_list = [config.preset, *deepcopy(config.preset_extension.backup_preset_list)]
    err: None | Exception = None
    if not preset_list:
        preset_list = ["default"]
    for name in preset_list:
        try:
            preset = await config_manager.get_preset(name, cache=False)

            if preset.protocol not in ("__main__", "openai"):
                continue
            base_url = preset.base_url
            key = preset.api_key
            model = preset.model

            logger.debug(f"开始获取 {preset.model} 的带有工具的对话")
            logger.debug(f"预设：{name}")
            logger.debug(f"密钥：{preset.api_key[:7]}...")
            logger.debug(f"协议：{preset.protocol}")
            logger.debug(f"API地址：{preset.base_url}")
            client = openai.AsyncOpenAI(
                base_url=base_url, api_key=key, timeout=config.llm_config.llm_timeout
            )
            completion: ChatCompletion = await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                tool_choice=tool_choice,
                tools=tools,
            )
            return completion.choices[0].message

        except Exception as e:
            logger.warning(f"[OpenAI] {name} 模型调用失败: {e}")
            err = e
            continue
    logger.warning("Tools调用因为没有OPENAI协议模型而失败")
    if err is not None:
        raise err
    return ChatCompletionMessage(role="assistant", content="")


async def get_chat(
    messages: list,
    bot: Bot | None = None,
    tokens: int = 0,
) -> str:
    """获取聊天响应"""
    # 获取最大token数量
    if bot is None:
        nb_bot = nonebot.get_bot()
        assert isinstance(nb_bot, Bot)
    else:
        nb_bot = bot
    max_tokens = config_manager.config.llm_config.max_tokens
    presets = [
        config_manager.config.preset,
        *config_manager.config.preset_extension.backup_preset_list,
    ]
    err: Exception | None = None
    for pname in presets:
        preset = await config_manager.get_preset(pname, cache=False)
        func = openai_get_chat
        # 根据预设选择API密钥和基础URL
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

        # 调用适配器获取聊天响应
        try:
            response = await func(
                preset.base_url,
                preset.model,
                preset.api_key,
                messages,
                max_tokens,
                config_manager.config,
                nb_bot,
            )
        except Exception as e:
            logger.warning(f"调用适配器失败{e}")
            err = e
            continue
        if chat_manager.debug:
            logger.debug(response)
        return remove_think_tag(response) if is_thought_chain_model else response
    if err is not None:
        raise err
    return ""


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
        base_url=base_url, api_key=key, timeout=config.llm_config.llm_timeout
    )
    completion: ChatCompletion | openai.AsyncStream[ChatCompletionChunk] | None = None
    # 尝试获取聊天响应，最多重试3次
    for index, i in enumerate(range(3)):
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                stream=config.llm_config.stream,
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
    if config.llm_config.stream and isinstance(completion, openai.AsyncStream):
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
] = {"openai": openai_get_chat}
