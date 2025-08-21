from __future__ import annotations

import typing
from collections.abc import Iterable
from copy import deepcopy

import openai
from nonebot import logger
from nonebot.adapters.onebot.v11 import Event
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_named_tool_choice_param import (
    ChatCompletionNamedToolChoiceParam,
)
from openai.types.chat.chat_completion_named_tool_choice_param import (
    Function as OPENAI_Function,
)
from openai.types.chat.chat_completion_tool_choice_option_param import (
    ChatCompletionToolChoiceOptionParam,
)
from typing_extensions import override

from nonebot_plugin_suggarchat.utils.llm_tools.models import ToolFunctionSchema
from nonebot_plugin_suggarchat.utils.protocol import ToolCall

from ..chatmanager import chat_manager
from ..check_rule import is_bot_admin
from ..config import config_manager
from ..utils.models import InsightsModel
from .functions import remove_think_tag
from .memory import BaseModel, Message, ToolResult, get_memory_data
from .protocol import (
    AdapterManager,
    ModelAdapter,
    ToolChoice,
    UniResponse,
    UniResponseUsage,
)


async def usage_enough(event: Event) -> bool:
    config = config_manager.config
    if not config.usage_limit.enable_usage_limit:
        return True
    if await is_bot_admin(event):
        return True

    # ### Starts of Global Insights ###
    global_insights = await InsightsModel.get()
    if (
        config.usage_limit.total_daily_limit != -1
        and global_insights.usage_count >= config.usage_limit.total_daily_limit
    ):
        return False

    if config.usage_limit.total_daily_token_limit != -1 and (
        global_insights.token_input + global_insights.token_output
        >= config.usage_limit.total_daily_token_limit
    ):
        return False

    # ### End of global insights ###

    # ### User insights ###
    user_id = int(event.get_user_id())
    data = await get_memory_data(user_id=user_id)
    if (
        data.usage >= config.usage_limit.user_daily_limit
        and config.usage_limit.user_daily_limit != -1
    ):
        return False
    if (
        config.usage_limit.user_daily_token_limit != -1
        and (data.input_token_usage + data.output_token_usage)
        >= config.usage_limit.user_daily_token_limit
    ):
        return False

    # ### End of user check ###

    # ### Start of group check ###

    if (gid := getattr(event, "group_id", None)) is not None:
        group_id = typing.cast(int, gid)
        data = await get_memory_data(group_id=group_id)

        if (
            config.usage_limit.group_daily_limit != -1
            and data.usage >= config.usage_limit.group_daily_limit
        ):
            return False
        if (
            config.usage_limit.group_daily_token_limit != -1
            and data.input_token_usage + data.output_token_usage
            >= config.usage_limit.group_daily_token_limit
        ):
            return False

    # ### End of group check ###

    return True


async def tools_caller(
    messages: Iterable,
    tools: list,
    tool_choice: ToolChoice | None = None,
):
    presets = [
        config_manager.config.preset,
        *config_manager.config.preset_extension.backup_preset_list,
    ]
    if not presets:
        raise ValueError("预设列表为空，无法继续处理。")
    err: Exception | None = None
    for pname in presets:
        preset = await config_manager.get_preset(pname)
        if adapter := AdapterManager().safe_get_adapter(preset.protocol):
            logger.debug(f"使用适配器 {adapter.__name__} 处理协议 {preset.protocol}")
        else:
            raise ValueError(f"未定义的协议适配器：{preset.protocol}")
        logger.debug(f"开始获取 {preset.model} 的带有工具的对话")
        logger.debug(f"预设：{pname}")
        logger.debug(f"密钥：{preset.api_key[:7]}...")
        logger.debug(f"协议：{preset.protocol}")
        logger.debug(f"API地址：{preset.base_url}")
        logger.debug(f"模型：{preset.model}")
        try:
            processer = adapter(preset, config_manager.config)
            response = await processer.call_tools(messages, tools, tool_choice)
            return response
        except NotImplementedError:
            continue
        except Exception as e:
            logger.warning(f"调用适配器失败{e}，正在尝试下一个Adapter")
            err = e
            continue
    else:
        raise err or RuntimeError("所有适配器调用失败")


async def get_chat(
    messages: list[Message | ToolResult],
) -> UniResponse[str, None]:
    """获取聊天响应"""
    presets = [
        config_manager.config.preset,
        *config_manager.config.preset_extension.backup_preset_list,
    ]
    assert presets
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
            response.content = (
                remove_think_tag(response.content)
                if is_thought_chain_model
                else response.content
            )
            if chat_manager.debug:
                logger.debug(response)
            return response
        except Exception as e:
            logger.warning(f"调用适配器失败{e}，正在尝试下一个Adapter")
            err = e
            continue
    else:
        logger.warning("所有适配器调用失败")
        raise err or Exception("所有适配器调用失败")


class OpenAIAdapter(ModelAdapter):
    """OpenAI协议适配器"""

    async def call_api(
        self, messages: Iterable[ChatCompletionMessageParam]
    ) -> UniResponse[str, None]:
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
        if config.llm_config.stream:
            completion = await client.chat.completions.create(
                model=preset.model,
                messages=messages,
                max_tokens=config.llm_config.max_tokens,
                stream=config.llm_config.stream,
                stream_options={"include_usage": True},
            )
        else:
            completion = await client.chat.completions.create(
                model=preset.model,
                messages=messages,
                max_tokens=config.llm_config.max_tokens,
                stream=config.llm_config.stream,
            )
        response: str = ""
        uni_usage = None
        # 处理流式响应
        if config.llm_config.stream and isinstance(completion, openai.AsyncStream):
            async for chunk in completion:
                try:
                    if chunk.usage:
                        uni_usage = UniResponseUsage.model_validate(
                            chunk.usage, from_attributes=True
                        )
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
                if completion.usage:
                    uni_usage = UniResponseUsage.model_validate(
                        completion.usage, from_attributes=True
                    )
            else:
                raise RuntimeError("收到意外的响应类型")
        uni_response = UniResponse(
            content=response,
            usage=uni_usage,
            tool_calls=None,
        )
        return uni_response

    @override
    async def call_tools(
        self,
        messages: Iterable,
        tools: list,
        tool_choice: ToolChoice | None = None,
    ) -> UniResponse[None, list[ToolCall] | None]:
        if not tool_choice:
            choice: ChatCompletionToolChoiceOptionParam = (
                "required"
                if (
                    config_manager.config.llm_config.tools.require_tools
                    and len(tools) > 1
                )  # 排除默认工具
                else "auto"
            )
        elif isinstance(tool_choice, ToolFunctionSchema):
            choice = ChatCompletionNamedToolChoiceParam(
                function=OPENAI_Function(name=tool_choice.function.name),
                type=tool_choice.type,
            )
        else:
            choice = tool_choice
        config = config_manager.config
        preset_list = [
            config.preset,
            *deepcopy(config.preset_extension.backup_preset_list),
        ]
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
                client = openai.AsyncOpenAI(
                    base_url=base_url,
                    api_key=key,
                    timeout=config.llm_config.llm_timeout,
                )
                completion: ChatCompletion = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=False,
                    tool_choice=choice,
                    tools=tools,
                )
                msg = completion.choices[0].message
                return UniResponse(
                    tool_calls=[
                        ToolCall.model_validate(i, from_attributes=True)
                        for i in msg.tool_calls
                    ]
                    if msg.tool_calls
                    else None,
                    content=None,
                )

            except Exception as e:
                logger.warning(f"[OpenAI] {name} 模型调用失败: {e}")
                err = e
                continue
        logger.warning("OpenAI协议Tools调用尝试失败")
        if err is not None:
            raise err
        return UniResponse(
            tool_calls=None,
            content=None,
        )

    @staticmethod
    def get_adapter_protocol() -> tuple[str, ...]:
        return "openai", "__main__"
