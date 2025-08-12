from __future__ import annotations

import typing
from collections.abc import Iterable
from copy import deepcopy

import openai
from nonebot import logger
from nonebot.adapters.onebot.v11 import Event
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_choice_option_param import (
    ChatCompletionToolChoiceOptionParam,
)

from nonebot_plugin_suggarchat.check_rule import is_bot_admin

from ..chatmanager import chat_manager
from ..config import config_manager
from .functions import remove_think_tag
from .memory import BaseModel, Message, ToolResult, get_memory_data
from .protocol import AdapterManager, ModelAdapter


async def usage_enough(event: Event) -> bool:
    config = config_manager.config
    if not config.usage_limit.enable_usage_limit:
        return True
    user_id = int(event.get_user_id())
    if await is_bot_admin(event):
        return True
    if config.usage_limit.user_daily_limit == -1:
        return True
    if (
        await get_memory_data(user_id=user_id)
    ).usage >= config.usage_limit.user_daily_limit:
        return False
    if hasattr(event, "group_id"):
        gid = getattr(event, "group_id")
        if gid is None:
            return True
        group_id = typing.cast(int, gid)
        if config.usage_limit.group_daily_limit == -1:
            return True
        if (
            await get_memory_data(group_id=group_id)
        ).usage >= config.usage_limit.group_daily_limit:
            return False

    return True


async def tools_caller(
    messages: Iterable,
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
            preset = await config_manager.get_preset(name)

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
    messages: list[Message | ToolResult],
    tokens: int = 0,
) -> str:
    """获取聊天响应"""
    presets = [
        config_manager.config.preset,
        *config_manager.config.preset_extension.backup_preset_list,
    ]
    err: Exception | None = None
    for pname in presets:
        preset = await config_manager.get_preset(pname)
        # 根据预设选择API密钥和基础URL
        is_thought_chain_model = preset.thought_chain_model
        if adapter := AdapterManager().safe_get_adapter(preset.protocol):
            # 如果适配器存在，使用它
            logger.debug(f"使用适配器 {adapter.__name__} 处理协议 {preset.protocol}")
        else:
            raise ValueError(f"未定义的协议适配器：{preset.protocol}")
        # 记录日志
        logger.debug(f"开始获取 {preset.model} 的对话")
        logger.debug(f"预设：{config_manager.config.preset}")
        logger.debug(f"密钥：{preset.api_key[:7]}...")
        logger.debug(f"协议：{preset.protocol}")
        logger.debug(f"API地址：{preset.base_url}")
        logger.debug(f"当前对话Tokens:{tokens}")
        response = ""
        # 调用适配器获取聊天响应
        try:
            processer = adapter(preset, config_manager.config)
            response = await processer.call_api(
                [
                    (
                        i.model_dump()
                        if isinstance(i, BaseModel)
                        else (
                            Message.model_validate(i)
                            if i["role"] != "tool"
                            else (ToolResult.model_validate(i))
                        ).model_dump()
                    )
                    for i in messages
                ]
            )
        except Exception as e:
            logger.warning(f"调用适配器失败{e}，正在尝试下一个Adapter")
            err = e
            continue
        else:
            err = None
        if chat_manager.debug:
            logger.debug(response)
        return remove_think_tag(response) if is_thought_chain_model else response
    if err is not None:
        raise err
    return ""


class OpenAIAdapter(ModelAdapter):
    """OpenAI协议适配器"""

    async def call_api(self, messages: Iterable[ChatCompletionMessageParam]) -> str:
        """调用OpenAI API获取聊天响应"""
        preset = self.preset
        config = self.config
        client = openai.AsyncOpenAI(
            base_url=preset.base_url,
            api_key=preset.api_key,
            timeout=config.llm_config.llm_timeout,
            max_retries=config.llm_config.max_retries,
        )
        completion: ChatCompletion | openai.AsyncStream[ChatCompletionChunk] | None = (
            None
        )

        completion = await client.chat.completions.create(
            model=preset.model,
            messages=messages,
            max_tokens=config.llm_config.max_tokens,
            stream=config.llm_config.stream,
        )
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

    @staticmethod
    def get_adapter_protocol() -> tuple[str, ...]:
        return "openai", "__main__"
