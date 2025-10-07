import json
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
from .utils.llm_tools.builtin_tools import REPORT_TOOL, STOP_TOOL, report
from .utils.llm_tools.manager import ToolsManager
from .utils.llm_tools.models import ToolContext
from .utils.memory import (
    Message,
    ToolResult,
    get_memory_data,
)

prehook = on_before_chat(block=False, priority=1)
posthook = on_chat(block=False, priority=1)

ChatException: TypeAlias = (
    BlockException | CancelException | PassException | NoneBotException
)


@prehook.handle()
async def rag_tools(event: BeforeChatEvent) -> None:
    async def run_tools(
        msg_list: list,
        nonebot_event: MessageEvent,
        call_count: int = 0,
        original_msg: str = "",
    ):
        if call_count > config_manager.config.llm_config.tools.agent_tool_call_limit:
            await bot.send(nonebot_event, "调用工具次数过多，Agent工作已终止。")
            return
        tools: list[dict[str, Any]] = []
        if config.llm_config.tools.enable_report:
            tools.append(REPORT_TOOL.model_dump(exclude_none=True))
        tools.extend(ToolsManager().tools_meta_dict(exclude_none=True).values())
        response_msg = await tools_caller(
            [
                *deepcopy([i for i in msg_list if i["role"] == "system"]),
                deepcopy(msg_list)[-1],
            ],
            tools,
        )
        if tool_calls := response_msg.tool_calls:
            msg_list.append(Message.model_validate(response_msg, from_attributes=True))
            result_msg_list: list[ToolResult] = []
            for tool_call in tool_calls:
                call_count += 1
                function_name = tool_call.function.name
                function_args: dict[str, Any] = json.loads(tool_call.function.arguments)
                logger.debug(f"函数参数为{tool_call.function.arguments}")
                logger.debug(f"正在调用函数{function_name}")
                match function_name:
                    case STOP_TOOL.function.name:
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
                    case REPORT_TOOL.function.name:
                        func_response = await report(
                            nonebot_event,
                            function_args.get("content", ""),
                            bot,
                        )
                        if config_manager.config.llm_config.tools.report_then_block:
                            data = await get_memory_data(nonebot_event)
                            data.memory.messages = []
                            await data.save(nonebot_event)
                            await bot.send(
                                nonebot_event,
                                random.choice(
                                    config_manager.config.llm_config.block_msg
                                ),
                            )
                            prehook.cancel_nonebot_process()
                    case _:
                        if (
                            tool_data := ToolsManager().get_tool(function_name)
                        ) is not None:
                            if not tool_data.custom_run:
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
                                func_response = tool_response
                        else:
                            logger.opt(exception=True, colors=True).error(
                                f"ChatHook中遇到了未定义的函数：{function_name}"
                            )
                            continue
                logger.debug(f"函数{function_name}返回：{func_response}")

                msg: ToolResult = ToolResult(
                    content=func_response,
                    name=function_name,
                    tool_call_id=tool_call.id,
                )
                msg_list.append(msg)
                result_msg_list.append(msg)
            if config_manager.config.llm_config.tools.agent_mode_enable:
                # 发送工具调用信息给用户
                await bot.send(
                    nonebot_event,
                    f"调用了函数{''.join([f'`{i.function.name}`,' for i in tool_calls])}",
                )
                observation_msg = "\n".join(
                    [
                        f"工具 {result.name} 的执行结果: {result.content}\n"
                        for result in result_msg_list
                    ]
                )
                msg_list.append(
                    Message(
                        role="user",
                        content=f"观察结果:\n{observation_msg}\n请基于以上工具执行结果继续完成任务，如果任务已完成请使用工具 '{STOP_TOOL.function.name}' 结束。",
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
    msg_list = event._send_message
    chat_list_backup = deepcopy(event.message.copy())

    try:
        await run_tools(
            msg_list, nonebot_event, original_msg=nonebot_event.get_plaintext()
        )

    except Exception as e:
        if isinstance(e, ChatException):
            raise
        logger.opt(colors=True, exception=e).exception(
            f"ERROR\n{e!s}\n!调用Tools失败！已旧数据继续处理..."
        )
        msg_list = chat_list_backup


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
