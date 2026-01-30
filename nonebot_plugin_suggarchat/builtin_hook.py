import json
import os
import random
import typing
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from nonebot import get_bot
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.log import logger

from .config import Config, ConfigManager
from .event import BeforeChatEvent, ChatEvent
from .matcher import ChatException
from .on_event import on_before_chat, on_chat
from .utils.admin import send_to_admin
from .utils.libchat import (
    tools_caller,
)
from .utils.llm_tools.builtin_tools import (
    PROCESS_MESSAGE,
    PROCESS_MESSAGE_TOOL,
    REASONING_TOOL,
    REPORT_TOOL_HIGH,
    REPORT_TOOL_LOW,
    REPORT_TOOL_MEDIUM,
    STOP_TOOL,
    report,
)
from .utils.llm_tools.manager import ToolsManager, on_tools
from .utils.llm_tools.models import ToolContext
from .utils.logging import debug_log
from .utils.memory import (
    get_memory_data,
)
from .utils.models import (
    SEND_MESSAGES,
    Message,
    ToolCall,
    ToolResult,
    UniResponse,
)

prehook = on_before_chat(block=False, priority=2)
checkhook = on_before_chat(block=False, priority=1)
posthook = on_chat(block=False, priority=1)


BUILTIN_TOOLS_NAME = {
    REPORT_TOOL_MEDIUM.function.name,
    STOP_TOOL.function.name,
    REASONING_TOOL.function.name,
    PROCESS_MESSAGE.function.name,
}

AGENT_PROCESS_TOOLS = (
    REASONING_TOOL,
    STOP_TOOL,
    PROCESS_MESSAGE,
)


class Continue(BaseException): ...


@checkhook.handle()
async def text_check(event: BeforeChatEvent) -> None:
    config: Config = ConfigManager().config
    if not config.llm_config.tools.enable_report:
        checkhook.pass_event()
    logger.info("Content checking in progress......")
    bot = get_bot()
    match config.llm_config.tools.report_invoke_level:
        case "low":
            tool_list = [REPORT_TOOL_LOW]
        case "medium":
            tool_list = [REPORT_TOOL_MEDIUM]
        case "high":
            tool_list = [REPORT_TOOL_HIGH]
        case _:
            raise ValueError("Invalid report_invoke_level")
    msg: SEND_MESSAGES = event._send_message.unwrap()
    if (
        config.llm_config.tools.report_exclude_context
        and config.llm_config.tools.report_exclude_system_prompt
    ):
        msg = [event.get_send_message().get_user_query()]
    elif config.llm_config.tools.report_exclude_system_prompt:
        msg = event.get_send_message().get_memory()
    elif config.llm_config.tools.report_exclude_context:
        msg = [
            event.get_send_message().get_train(),
            event.get_send_message().get_user_query(),
        ]
    if not msg:
        logger.warning("Message list is empty, skipping content check")
        return
    response: UniResponse[None, list[ToolCall] | None] = await tools_caller(
        msg, tool_list
    )
    nonebot_event = typing.cast(MessageEvent, event.get_nonebot_event())
    if tool_calls := response.tool_calls:
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args: dict[str, Any] = json.loads(tool_call.function.arguments)
            if function_name == REPORT_TOOL_MEDIUM.function.name:
                if not function_args.get("invoke"):
                    return
                await report(
                    event,
                    function_args,
                    typing.cast(Bot, bot),
                )
                if ConfigManager().config.llm_config.tools.report_then_block:
                    data = await get_memory_data(nonebot_event)
                    data.memory.messages = []
                    await data.save(nonebot_event)
                    await bot.send(
                        nonebot_event,
                        random.choice(ConfigManager().config.llm_config.block_msg),
                    )
                    prehook.cancel_nonebot_process()
            else:
                await send_to_admin(
                    f"[LLM-Report] Detected non-passed tool call: {function_name}, please feedback this issue to the model provider."
                )


@on_tools(
    data=PROCESS_MESSAGE_TOOL,
    custom_run=True,
    show_call=False,
    enable_if=lambda: ConfigManager().config.llm_config.tools.agent_middle_message,
)
async def _(ctx: ToolContext) -> str | None:
    msg: str = ctx.data["content"]
    debug_log(f"[LLM-ProcessMessage] {msg}")
    await ctx.bot.send(ctx.event.get_nonebot_event(), msg)
    return f"Sent a message to user:\n\n```text\n{msg}\n```\n"


@prehook.handle()
async def agent_core(event: BeforeChatEvent) -> None:
    agent_last_step: str = ""

    async def _append_reasoning(
        msg: SEND_MESSAGES, response: UniResponse[None, list[ToolCall] | None]
    ):
        nonlocal agent_last_step
        tool_calls: list[ToolCall] | None = response.tool_calls
        if tool_calls:
            for tool in tool_calls:
                if tool.function.name == REASONING_TOOL.function.name:
                    break
            else:
                raise ValueError(f"No reasoning tool found in response \n\n{response}")
            if reasoning := json.loads(tool.function.arguments).get("content"):
                msg.append(Message.model_validate(response, from_attributes=True))
                msg.append(
                    ToolResult(
                        role="tool",
                        name=tool.function.name,
                        content=reasoning,
                        tool_call_id=tool.id,
                    )
                )
                agent_last_step = reasoning
                debug_log(f"[AmritaAgent] {reasoning}")
                if not config.llm_config.tools.agent_reasoning_hide:
                    await bot.send(nonebot_event, f"[AmritaAgent] {reasoning}")
            else:
                raise ValueError("Reasoning tool has no content!")

    async def append_reasoning_msg(
        msg: SEND_MESSAGES,
        original_msg: str = "",
        last_step: str = "",
        tools_ctx: list[dict[str, Any]] = [],
    ):
        nonlocal agent_last_step
        reasoning_msg = [
            Message(
                role="system",
                content="Please analyze the task requirements based on the user input above,"
                + " summarize the current step's purpose and reasons, and execute accordingly."
                + " If no task needs to be performed, no description is needed;"
                + " please analyze according to the character tone set in <SYS_SETTINGS> (if present)."
                + (
                    f"\nYour previous task was:\n```text\n{last_step}\n```\n"
                    if last_step
                    else ""
                )
                + (f"\n<INPUT>\n{original_msg}\n</INPUT>\n" if original_msg else "")
                + (
                    f"<SYS_SETTINGS>\n{event._send_message.train.content!s}\n</SYS_SETTINGS>"
                ),
            ),
            *deepcopy(msg),
        ]
        response: UniResponse[None, list[ToolCall] | None] = await tools_caller(
            reasoning_msg, [REASONING_TOOL.model_dump(), *tools_ctx], REASONING_TOOL
        )
        await _append_reasoning(msg, response)

    async def run_tools(
        msg_list: list,
        nonebot_event: MessageEvent,
        call_count: int = 1,
        original_msg: str = "",
    ):
        suggested_stop: bool = False

        def stop_running():
            """Mark agent workflow as completed."""
            nonlocal suggested_stop
            suggested_stop = True

        logger.debug(
            f"Starting round {call_count} tool call, current message count: {len(msg_list)}"
        )
        if ConfigManager().config.llm_config.tools.agent_mode_enable and (
            (
                call_count == 1
                and ConfigManager().config.llm_config.tools.agent_thought_mode
                == "reasoning"
            )
            or ConfigManager().config.llm_config.tools.agent_thought_mode
            == "reasoning-required"
        ):
            await append_reasoning_msg(msg_list, original_msg, tools_ctx=tools)

        if call_count > ConfigManager().config.llm_config.tools.agent_tool_call_limit:
            await bot.send(
                nonebot_event, "[AmritaAgent] 过多次的工具调用！已中止Workflow！"
            )
            msg_list.append(
                Message(
                    role="user",
                    content="Too much tools called,please call later or follow user's instruction."
                    + "Now please continue to completion.",
                )
            )
            return
        response_msg = await tools_caller(
            msg_list,
            tools,
            (
                "required"
                if (
                    ConfigManager().config.llm_config.tools.require_tools
                    and not suggested_stop
                )
                else "auto"
            ),
        )

        if tool_calls := response_msg.tool_calls:
            result_msg_list: list[ToolResult] = []
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args: dict[str, Any] = json.loads(tool_call.function.arguments)
                logger.debug(f"Function arguments are {tool_call.function.arguments}")
                logger.debug(f"Calling function {function_name}")
                try:
                    match function_name:
                        case REASONING_TOOL.function.name:
                            logger.debug("Generating task summary and reason.")
                            await _append_reasoning(msg_list, response=response_msg)
                            raise Continue()
                        case STOP_TOOL.function.name:
                            logger.debug("Agent work has been terminated.")
                            func_response = (
                                "You have indicated readiness to provide the final answer."
                                + "Please now generate the final, comprehensive response for the user."
                            )
                            if "result" in function_args:
                                logger.debug(f"[Done] {function_args['result']}")
                                func_response += (
                                    f"\nWork summary :\n{function_args['result']}"
                                )
                            msg_list.append(
                                Message.model_validate(
                                    response_msg, from_attributes=True
                                )
                            )

                            stop_running()
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
                                    func_response = "(this tool returned no content)"
                                else:
                                    msg_list.append(
                                        Message.model_validate(
                                            response_msg, from_attributes=True
                                        )
                                    )
                                    func_response = tool_response
                            else:
                                logger.opt(exception=True, colors=True).error(
                                    f"Encountered undefined function in ChatHook: {function_name}"
                                )
                                continue
                except Continue:
                    continue
                except Exception as e:
                    if isinstance(e, ChatException):
                        raise
                    logger.warning(f"Function {function_name} execution failed: {e}")
                    if (
                        ConfigManager().config.llm_config.tools.agent_mode_enable
                        and function_name not in BUILTIN_TOOLS_NAME
                        and ConfigManager().config.llm_config.tools.agent_tool_call_notice
                    ):
                        await bot.send(
                            nonebot_event, f"ERR: Tool {function_name} 执行失败"
                        )
                    msg_list.append(
                        ToolResult(
                            role="tool",
                            name=function_name,
                            content=f"ERR: Tool {function_name} execution failed\n{e!s}",
                            tool_call_id=tool_call.id,
                        )
                    )
                    continue
                else:
                    logger.debug(f"Function {function_name} returned: {func_response}")

                    msg: ToolResult = ToolResult(
                        role="tool",
                        content=func_response,
                        name=function_name,
                        tool_call_id=tool_call.id,
                    )
                    msg_list.append(msg)
                    result_msg_list.append(msg)
                finally:
                    call_count += 1
            if ConfigManager().config.llm_config.tools.agent_mode_enable:
                # 发送工具调用信息给用户
                if (
                    ConfigManager().config.llm_config.tools.agent_tool_call_notice
                    == "notify"
                ):
                    if message := (
                        "".join(
                            f"✅ 调用了工具 {i.name}\n"
                            for i in result_msg_list
                            if (
                                getattr(
                                    ToolsManager().get_tool(i.name), "on_call", None
                                )
                                == "show"
                                and i.name not in AGENT_PROCESS_TOOLS
                            )
                        )
                    ):
                        await bot.send(nonebot_event, message)

                await run_tools(msg_list, nonebot_event, call_count, original_msg)

    config = ConfigManager().config
    if not config.llm_config.tools.enable_tools:
        return
    nonebot_event = event.get_nonebot_event()
    if not isinstance(nonebot_event, MessageEvent):
        return
    bot = typing.cast(Bot, get_bot(str(nonebot_event.self_id)))
    msg_list: SEND_MESSAGES = (
        [
            deepcopy(event.message.train),
            deepcopy(event.message.user_query),
        ]
        if config.llm_config.tools.use_minimal_context
        else event.message.unwrap()
    )
    current_length = len(msg_list)
    chat_list_backup = event.message.copy()
    tools: list[dict[str, Any]] = []
    if config.llm_config.tools.agent_mode_enable:
        tools.append(STOP_TOOL.model_dump())
        if config.llm_config.tools.agent_thought_mode.startswith("reasoning"):
            tools.append(REASONING_TOOL.model_dump())
    tools.extend(ToolsManager().tools_meta_dict().values())
    logger.debug(
        "工具列表："
        + "".join(
            f"{tool['function']['name']}: {tool['function']['description']}\n\n"
            for tool in tools
        )
    )
    debug_log(f"工具列表：{tools}")
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
        event._send_message.memory.extend(msg_list[current_length:])

    except Exception as e:
        if isinstance(e, ChatException):
            raise
        logger.opt(colors=True, exception=e).exception(
            f"ERROR\n{e!s}\n!Failed to call Tools! Continuing with old data..."
        )
        event._send_message = chat_list_backup


@posthook.handle()
async def cookie(event: ChatEvent, bot: Bot):
    config = ConfigManager().config
    response = event.get_model_response()
    nonebot_event = event.get_nonebot_event()
    if config.cookies.enable_cookie:
        if cookie := config.cookies.cookie:
            if cookie in response:
                await send_to_admin(
                    f"WARNING!!!\n[{nonebot_event.get_user_id()}]{'[群' + str(getattr(nonebot_event, 'group_id', '')) + ']' if hasattr(nonebot_event, 'group_id') else ''}用户输入导致了可能的Prompt泄露！！"
                    + f"\nCookie:{cookie[:3]}......"
                    + f"\n<input>\n{nonebot_event.get_plaintext()}\n</input>\n"
                    + "输出已包含目标Cookie！已阻断消息。"
                )
                data = await get_memory_data(nonebot_event)
                data.memory.messages = []
                await data.save(nonebot_event)
                await bot.send(
                    nonebot_event,
                    random.choice(ConfigManager().config.llm_config.block_msg),
                )
                posthook.cancel_nonebot_process()
