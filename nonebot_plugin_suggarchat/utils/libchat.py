from __future__ import annotations

import time
import typing
from collections.abc import Generator, Iterable
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
from pydantic import ValidationError
from typing_extensions import override

from nonebot_plugin_suggarchat.utils.logging import debug_log
from nonebot_plugin_suggarchat.utils.models import SEND_MESSAGES
from nonebot_plugin_suggarchat.utils.tokenizer import hybrid_token_count

from ..config import ConfigManager, ModelPreset
from ..utils.llm_tools.models import ToolFunctionSchema
from ..utils.models import InsightsModel
from ..utils.protocol import ToolCall
from .functions import remove_think_tag
from .llm_tools.models import ToolChoice
from .memory import BaseModel, get_memory_data
from .models import (
    Message,
    TextContent,
    ToolResult,
    UniResponse,
    UniResponseUsage,
)
from .protocol import (
    AdapterManager,
    ModelAdapter,
)

TEST_MSG_PROMPT: Message[list[TextContent]] = Message(
    role="system",
    content=[TextContent(text="You are a helpful assistant.", type="text")],
)
TEST_MSG_USER: Message[list[TextContent]] = Message(
    role="user", content=[TextContent(text="你好，请简要介绍你自己。", type="text")]
)

TEST_MSG_LIST: list[Message[list[TextContent]]] = [
    TEST_MSG_PROMPT,
    TEST_MSG_USER,
]


class PresetReport(BaseModel):
    preset_name: str  # 预设名称
    preset_data: ModelPreset  # 预设数据
    test_input: tuple[Message, Message]  # 测试输入
    test_output: Message | None  # 测试输出
    token_prompt: int  # 提示词的token数
    token_completion: int  # 回复的token数
    status: bool  # 测试结果
    message: str  # 测试结果信息
    time_used: float


async def test_single_preset(preset: ModelPreset) -> PresetReport:
    """测试单个预设，用于并行执行"""
    logger.debug(f"正在测试预设：{preset.name}...")
    prompt_tokens = hybrid_token_count(
        "".join(
            [typing.cast(TextContent, msg.content[0]).text for msg in TEST_MSG_LIST]
        )
    )

    adapter = AdapterManager().safe_get_adapter(preset.protocol)
    if adapter is None:
        logger.warning(f"未定义的协议适配器：{preset.protocol}")
        return PresetReport(
            preset_name=preset.name,
            preset_data=preset,
            test_input=(TEST_MSG_PROMPT, TEST_MSG_USER),
            test_output=None,
            token_prompt=prompt_tokens,
            token_completion=0,
            status=False,
            message=f"未定义的协议适配器: {preset.protocol}",
            time_used=0,
        )

    try:
        time_start = time.time()
        logger.debug(f"正在调用预设：{preset.name}...")
        data = await adapter(preset, ConfigManager().config).call_api(TEST_MSG_LIST)
        time_end = time.time()
        time_delta = time_end - time_start
        logger.debug(f"调用预设 {preset.name} 成功，耗时 {time_delta:.2f} 秒")
        return PresetReport(
            preset_name=preset.name,
            preset_data=preset,
            test_input=(TEST_MSG_PROMPT, TEST_MSG_USER),
            test_output=Message[list[TextContent]](
                role="assistant",
                content=[TextContent(type="text", text=data.content)],
            ),
            token_prompt=prompt_tokens,
            token_completion=hybrid_token_count(data.content),
            status=True,
            message="",
            time_used=time_delta,
        )
    except Exception as e:
        logger.error(f"测试预设 {preset.name} 时发生错误：{e}")
        return PresetReport(
            preset_name=preset.name,
            preset_data=preset,
            test_input=(TEST_MSG_PROMPT, TEST_MSG_USER),
            test_output=None,
            token_prompt=prompt_tokens,
            token_completion=0,
            status=False,
            message=str(e),
            time_used=0,
        )


async def test_presets() -> typing.AsyncGenerator[PresetReport, None]:
    presets = await ConfigManager().get_all_presets(True)
    logger.debug(f"开始测试所有(共计{len(presets)}个)预设...")
    for preset in presets:
        yield await test_single_preset(preset)


def text_generator(
    memory: SEND_MESSAGES, split_role: bool = False
) -> Generator[str, None, str]:
    memory_l = [(i.model_dump() if hasattr(i, "model_dump") else i) for i in memory]
    role_map = {
        "assistant": "<BOT的回答>",
        "user": "<用户的提问>",
        "tool": "<工具调用>",
    }
    for st in memory_l:
        if st["content"] is None:
            continue
        if isinstance(st["content"], str):
            yield (
                st["content"]
                if not split_role
                else role_map.get(st["role"], "") + st["content"]
            )
        else:
            for s in st["content"]:
                if s["type"] == "text" and s.get("text") is not None:
                    yield (
                        s["text"]
                        if not split_role
                        else role_map.get(st["role"], "") + s["text"]
                    )
    return ""


async def get_tokens(
    memory: SEND_MESSAGES, response: UniResponse[str, None]
) -> UniResponseUsage[int]:
    """计算消息和响应的token数量

    Args:
        memory: 消息历史列表
        response: 模型响应

    Returns:
        包含token使用情况的对象
    """
    if (
        response.usage is not None
        and response.usage.total_tokens is not None
        and response.usage.completion_tokens is not None
        and response.usage.prompt_tokens is not None
    ):
        return response.usage

    it = hybrid_token_count(
        "".join(list(text_generator(memory))),
        ConfigManager().config.llm_config.tokens_count_mode,
    )

    ot = hybrid_token_count(response.content)
    return UniResponseUsage(
        prompt_tokens=it, total_tokens=it + ot, completion_tokens=ot
    )


async def usage_enough(event: Event) -> bool:
    from ..check_rule import is_bot_admin

    config = ConfigManager().config
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


def _validate_msg_list(
    messages: SEND_MESSAGES,
) -> SEND_MESSAGES:
    validated_messages = []
    for msg in messages:
        if isinstance(msg, dict):
            # 确保消息有 role 字段
            if "role" not in msg:
                raise ValueError("Message dictionary is missing 'role' field")
            try:
                validated_msg = (
                    Message.model_validate(msg)
                    if msg["role"] != "tool"
                    else ToolResult.model_validate(msg)
                )
            except ValidationError as e:
                raise ValueError(f"Invalid message format: {e}")
            validated_messages.append(validated_msg)
        else:
            validated_messages.append(msg)
    return validated_messages


async def _determine_presets(
    messages: SEND_MESSAGES,
) -> list[str]:
    """根据消息内容确定使用的预设列表"""
    # 检查消息中是否包含非文本内容（如图片等）
    has_multimodal_content = False
    msg_list = _validate_msg_list(messages)
    for msg in msg_list:
        if isinstance(msg.content, str) or not msg.content:
            continue
        has_multimodal_content = any(
            not isinstance(content, TextContent) for content in msg.content
        )

        if has_multimodal_content:
            break

    config = ConfigManager().config
    if has_multimodal_content:
        multimodal_presets = config.preset_extension.multi_modal_preset_list or [
            config.preset,
        ] + [
            preset
            for preset in config.preset_extension.backup_preset_list
            if (await ConfigManager().get_preset(preset)).multimodal
        ]
        return multimodal_presets
    else:
        return [
            config.preset,
            *config.preset_extension.backup_preset_list,
        ]


async def _call_with_presets(
    presets: list[str],
    call_func: typing.Callable[..., typing.Awaitable[UniResponse]],
    *args,
    **kwargs,
) -> UniResponse:
    """使用预设列表调用指定函数"""
    if not presets:
        raise ValueError("预设列表为空，无法继续处理。")

    err: Exception | None = None
    for pname in presets:
        preset = await ConfigManager().get_preset(pname)
        adapter_class = AdapterManager().safe_get_adapter(preset.protocol)
        if adapter_class:
            logger.debug(
                f"使用适配器 {adapter_class.__name__} 处理协议 {preset.protocol}"
            )
        else:
            raise ValueError(f"未定义的协议适配器：{preset.protocol}")

        logger.debug(f"开始获取 {preset.model} 的对话")
        logger.debug(f"预设：{pname}")
        logger.debug(f"密钥：{preset.api_key[:7]}...")
        logger.debug(f"协议：{preset.protocol}")
        logger.debug(f"API地址：{preset.base_url}")
        logger.debug(f"模型：{preset.model}")

        try:
            adapter = adapter_class(preset, ConfigManager().config)
            return await call_func(adapter, *args, **kwargs)
        except NotImplementedError:
            continue
        except Exception as e:
            logger.warning(f"调用适配器失败{e}，正在尝试下一个Adapter")
            err = e
            continue
    else:
        raise err or RuntimeError("所有适配器调用失败")


async def tools_caller(
    messages: SEND_MESSAGES,
    tools: list,
    tool_choice: ToolChoice | None = None,
) -> UniResponse[None, list[ToolCall] | None]:
    presets = await _determine_presets(messages)

    async def _call_tools(
        adapter: ModelAdapter,
        messages: SEND_MESSAGES,
        tools,
        tool_choice,
    ):
        return await adapter.call_tools(messages, tools, tool_choice)

    return await _call_with_presets(presets, _call_tools, messages, tools, tool_choice)


async def get_chat(
    messages: SEND_MESSAGES,
) -> UniResponse[str, None]:
    """获取聊天响应"""
    messages = _validate_msg_list(messages)
    presets = await _determine_presets(messages)

    async def _call_api(adapter: ModelAdapter, messages: SEND_MESSAGES):
        response = await adapter.call_api([(i.model_dump()) for i in messages])
        preset = adapter.preset
        if preset.thought_chain_model:
            response.content = remove_think_tag(response.content)
        return response

    # 调用适配器获取聊天响应
    response = await _call_with_presets(presets, _call_api, messages)

    debug_log(str(response))
    return response


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
                        debug_log(chunk.choices[0].delta.content)
                except IndexError:
                    break
        else:
            debug_log(response)
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
            role="assistant",
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
            choice: ChatCompletionToolChoiceOptionParam = "auto"
        elif isinstance(tool_choice, ToolFunctionSchema):
            choice = ChatCompletionNamedToolChoiceParam(
                function=OPENAI_Function(name=tool_choice.function.name),
                type=tool_choice.type,
            )
        else:
            choice = tool_choice
        config = ConfigManager().config
        preset_list = [
            config.preset,
            *deepcopy(config.preset_extension.backup_preset_list),
        ]
        err: None | Exception = None
        if not preset_list:
            preset_list = ["default"]
        for name in preset_list:
            try:
                preset = await ConfigManager().get_preset(name)

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
                    role="assistant",
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
            role="assistant",
            tool_calls=None,
            content=None,
        )

    @staticmethod
    def get_adapter_protocol() -> tuple[str, ...]:
        return "openai", "__main__"
