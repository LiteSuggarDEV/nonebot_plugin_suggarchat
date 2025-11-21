import json
import os
import random
import typing
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any, TypeAlias

from nonebot import get_bot
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.exception import NoneBotException
from nonebot.log import logger

from .config import config_manager
from .event import BeforeChatEvent, ChatEvent
from .exception import (
    BlockException,
    CancelException,
    PassException,
)
from .on_event import on_before_chat, on_chat
from .utils.admin import send_to_admin
from .utils.libchat import (
    tools_caller,
)
from .utils.llm_tools.builtin_tools import (
    REASONING_TOOL,
    REPORT_TOOL,
    STOP_TOOL,
    report,
)
from .utils.llm_tools.manager import ToolsManager
from .utils.llm_tools.models import ToolContext
from .utils.memory import (
    Message,
    ToolResult,
    get_memory_data,
)

prehook = on_before_chat(block=False, priority=2)
checkhook = on_before_chat(block=False, priority=1)
posthook = on_chat(block=False, priority=1)

ChatException: TypeAlias = (
    BlockException | CancelException | PassException | NoneBotException
)

BUILTIN_TOOLS_NAME = {
    REPORT_TOOL.function.name,
    STOP_TOOL.function.name,
    REASONING_TOOL.function.name,
}

AGENT_PROCESS_TOOLS = (
    REASONING_TOOL,
    STOP_TOOL,
)


@checkhook.handle()
async def text_check(event: BeforeChatEvent) -> None:
    config = config_manager.config
    if not config.llm_config.tools.enable_report:
        checkhook.pass_event()
    logger.info("正在进行内容审查......")
    bot = get_bot()
    tool_list = [REPORT_TOOL]
    msg = event._send_message
    if config.llm_config.tools.report_exclude_system_prompt:
        msg = msg[1:]
    if config.llm_config.tools.report_exclude_context:
        msg = msg[:-1]
    response = await tools_caller(msg, tool_list)
    nonebot_event = typing.cast(MessageEvent, event.get_nonebot_event())
    if tool_calls := response.tool_calls:
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args: dict[str, Any] = json.loads(tool_call.function.arguments)
            if function_name == REPORT_TOOL.function.name:
                await report(
                    nonebot_event,
                    function_args.get("content", ""),
                    typing.cast(Bot, bot),
                )
                if config_manager.config.llm_config.tools.report_then_block:
                    data = await get_memory_data(nonebot_event)
                    data.memory.messages = []
                    await data.save(nonebot_event)
                    await bot.send(
                        nonebot_event,
                        random.choice(config_manager.config.llm_config.block_msg),
                    )
                    prehook.cancel_nonebot_process()
            else:
                await send_to_admin(
                    f"[LLM-Report] 检测到非传入工具调用：{function_name}，请向模型提供商反馈此问题。"
                )


@prehook.handle()
async def agent_core(event: BeforeChatEvent) -> None:
    agent_last_step = [""]

    async def append_reasoning_msg(
        msg: list,
        original_msg: str = "",
        last_step: str = "",
    ):
        reasoning_msg = [
            Message(
                role="system",
                content="请根据上文用户输入，分析任务需求，并给出你该步应执行的摘要与原因，如果不需要执行任务则不需要填写描述。"
                + (
                    f"\n你的上一步任务为：\n```text\n{last_step}\n```\n"
                    if last_step
                    else ""
                )
                + (f"\n<INPUT>{original_msg}</INPUT>\n" if original_msg else ""),
            ),
            *msg,
        ]
        response = await tools_caller(reasoning_msg, [REASONING_TOOL])
        tool_calls = response.tool_calls
        if tool_calls:
            tool = tool_calls[0]
            if reasoning := json.loads(tool.function.arguments).get("reasoning"):
                agent_last_step[0] = reasoning
                await bot.send(nonebot_event, f"[Agent] {reasoning}")
                msg.append(Message.model_validate(response, from_attributes=True))
                msg.append(
                    ToolResult(
                        role="tool",
                        name=tool.function.name,
                        content=reasoning,
                        tool_call_id=tool.id,
                    )
                )

    async def run_tools(
        msg_list: list,
        nonebot_event: MessageEvent,
        call_count: int = 0,
        original_msg: str = "",
    ):
        logger.debug(f"开始第{call_count + 1}轮工具调用，当前消息数: {len(msg_list)}")
        if config_manager.config.llm_config.tools.agent_mode_enable and (
            (
                call_count == 0
                and config_manager.config.llm_config.tools.agent_thought_mode
                == "reasoning"
            )
            or config_manager.config.llm_config.tools.agent_thought_mode
            == "reasoning-required"
        ):
            await append_reasoning_msg(msg_list, original_msg)

        if call_count > config_manager.config.llm_config.tools.agent_tool_call_limit:
            await bot.send(nonebot_event, "调用工具次数过多，Agent工作已终止。")
            return
        response_msg = await tools_caller(
            msg_list,
            tools,
        )
        if tool_calls := response_msg.tool_calls:
            result_msg_list: list[ToolResult] = []
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args: dict[str, Any] = json.loads(tool_call.function.arguments)
                logger.debug(f"函数参数为{tool_call.function.arguments}")
                logger.debug(f"正在调用函数{function_name}")
                try:
                    match function_name:
                        case REASONING_TOOL.function.name:
                            logger.debug("正在生成任务摘要与原因。")
                            await append_reasoning_msg(
                                msg_list,
                                original_msg,
                                agent_last_step[0],
                            )
                            continue
                        case STOP_TOOL.function.name:
                            logger.debug("Agent工作已终止。")
                            msg_list.append(
                                Message(
                                    role="user",
                                    content="你已经完成了聊天前任务，请继续完成对话补全。"
                                    + (
                                        f"\n<INPUT>{original_msg}</INPUT>"
                                        if original_msg
                                        else ""
                                    ),
                                )
                            )
                            return
                        case _:
                            if (
                                tool_data := ToolsManager().get_tool(function_name)
                            ) is not None:
                                if not tool_data.custom_run:
                                    msg_list.append(
                                        Message.model_validate(
                                            response_msg, from_attributes=True
                                        )
                                    )
                                    func_response: str = await typing.cast(
                                        Callable[[dict[str, Any]], Awaitable[str]],
                                        tool_data.func,
                                    )(function_args)
                                elif (
                                    tool_response := await typing.cast(
                                        Callable[[ToolContext], Awaitable[str | None]],
                                        tool_data.func,
                                    )(
                                        ToolContext(
                                            data=function_args,
                                            event=event,
                                            matcher=prehook,
                                            bot=bot,
                                        )
                                    )
                                ) is None:
                                    continue
                                else:
                                    msg_list.append(
                                        Message.model_validate(
                                            response_msg, from_attributes=True
                                        )
                                    )
                                    func_response = tool_response
                            else:
                                logger.opt(exception=True, colors=True).error(
                                    f"ChatHook中遇到了未定义的函数：{function_name}"
                                )
                                continue
                except Exception as e:
                    if isinstance(e, ChatException):
                        raise
                    logger.warning(f"函数{function_name}执行失败：{e}")
                    if (
                        config_manager.config.llm_config.tools.agent_mode_enable
                        and function_name not in BUILTIN_TOOLS_NAME
                    ):
                        await bot.send(
                            nonebot_event, f"ERR: Tool {function_name} 执行失败"
                        )
                    msg_list.append(
                        ToolResult(
                            name=function_name,
                            content=f"ERR: Tool {function_name} 执行失败\n{e!s}",
                            tool_call_id=tool_call.id,
                        )
                    )
                    continue
                else:
                    logger.debug(f"函数{function_name}返回：{func_response}")

                    msg: ToolResult = ToolResult(
                        content=func_response,
                        name=function_name,
                        tool_call_id=tool_call.id,
                    )
                    msg_list.append(msg)
                    result_msg_list.append(msg)
                finally:
                    call_count += 1
            if config_manager.config.llm_config.tools.agent_mode_enable:
                # 发送工具调用信息给用户
                await bot.send(
                    nonebot_event,
                    f"调用了函数{''.join([f'`{i.function.name}`,' for i in tool_calls])}",
                )
                observation_msg = "\n".join(
                    [f"{result.name}: {result.content}\n" for result in result_msg_list]
                )
                msg_list.append(
                    Message(
                        role="user",
                        content=f"观察结果:\n```text\n{observation_msg}\n```"
                        + f"\n请基于以上工具执行结果继续完成任务，如果任务已完成请使用工具 '{STOP_TOOL.function.name}' 结束。",
                    )
                )
                await run_tools(msg_list, nonebot_event, call_count, original_msg)

    config = config_manager.config
    if not config.llm_config.tools.enable_tools:
        return
    nonebot_event = event.get_nonebot_event()
    if not isinstance(nonebot_event, MessageEvent):
        return
    bot = typing.cast(Bot, get_bot(str(nonebot_event.self_id)))
    msg_list = [
        *deepcopy([i for i in event.message if i["role"] == "system"]),
        deepcopy(event.message)[-1],
    ]
    chat_list_backup = deepcopy(event.message.copy())
    tools: list[dict[str, Any]] = []
    if config.llm_config.tools.agent_mode_enable:
        tools.append(STOP_TOOL.model_dump())
        if config.llm_config.tools.agent_thought_mode.startswith("reasoning"):
            tools.append(REASONING_TOOL.model_dump(exclude_none=True))
    tools.extend(ToolsManager().tools_meta_dict(exclude_none=True).values())
    logger.debug(f"工具列表：{tools}")
    if not tools:
        logger.warning("未定义任何有效工具！Tools Workflow已跳过。")
        return
    if str(os.getenv("AMRITA_IGNORE_AGENT_TOOLS")).lower() == "true" and (
        config.llm_config.tools.agent_mode_enable
        and len(tools) == len(AGENT_PROCESS_TOOLS)
    ):
        logger.warning(
            "注意：当前工具类型仅有Agent模式过程工具，而无其他有效工具定义，这通常不是使用Agent模式的最佳实践。配置环境变量AMRITA_IGNORE_AGENT_TOOLS=true可忽略此警告。"
        )

    try:
        await run_tools(
            msg_list, nonebot_event, original_msg=nonebot_event.get_plaintext()
        )
        event._send_message.extend(
            [msg for msg in msg_list if msg not in event._send_message]
        )

    except Exception as e:
        if isinstance(e, ChatException):
            raise
        logger.opt(colors=True, exception=e).exception(
            f"ERROR\n{e!s}\n!调用Tools失败！已旧数据继续处理..."
        )
        event._send_message = chat_list_backup


@posthook.handle()
async def cookie(event: ChatEvent, bot: Bot):
    config = config_manager.config
    response = event.get_model_response()
    nonebot_event = event.get_nonebot_event()
    if config.cookies.enable_cookie:
        if cookie := config.cookies.cookie:
            if cookie in response:
                await send_to_admin(
                    f"WARNING!!!\n[{nonebot_event.get_user_id()}]{'[群' + str(getattr(nonebot_event, 'group_id', '')) + ']' if hasattr(nonebot_event, 'group_id') else ''}用户尝试套取提示词！！！"
                    + f"\nCookie:{cookie[:3]}......"
                    + f"\n<input>\n{nonebot_event.get_plaintext()}\n</input>\n"
                    + "输出已包含目标Cookie！已阻断消息。"
                )
                data = await get_memory_data(nonebot_event)
                data.memory.messages = []
                await data.save(nonebot_event)
                await bot.send(
                    nonebot_event,
                    random.choice(config_manager.config.llm_config.block_msg),
                )
                posthook.cancel_nonebot_process()
