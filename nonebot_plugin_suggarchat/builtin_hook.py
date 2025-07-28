import json
import random
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
from .utils.llm_tools.builtin_tools import REPORT_TOOL, report
from .utils.llm_tools.manager import ToolsManager
from .utils.memory import (
    get_memory_data,
    write_memory_data,
)

prehook = on_before_chat(block=False, priority=1)
posthook = on_chat(block=False, priority=1)

ChatException: TypeAlias = (
    BlockException | CancelException | PassException | NoneBotException
)


@prehook.handle()
async def love_handler(event: BeforeChatEvent) -> None:
    config = config_manager.config
    if not config.llm_config.tools.enable_tools:
        return
    nonebot_event = event.get_nonebot_event()
    if not isinstance(nonebot_event, MessageEvent):
        return
    bot = get_bot(str(nonebot_event.self_id))
    try:
        assert isinstance(bot, Bot), "bot is not ~.onebot.v11.Bot!"
        msg_list = event._send_message
        chat_list_backup = deepcopy(event.message.copy())

        try:
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
            tool_calls = response_msg.tool_calls
            if tool_calls:
                msg_list.append(dict(response_msg))
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args: dict = json.loads(tool_call.function.arguments)
                    logger.debug(f"函数参数为{tool_call.function.arguments}")
                    logger.debug(f"正在调用函数{function_name}")
                    match function_name:
                        case "report":
                            func_response = await report(
                                nonebot_event,
                                function_args.get("content", ""),
                                bot,
                            )
                        case _:
                            if (
                                func := ToolsManager().get_tool_func(function_name)
                            ) is not None:
                                func_response = await func(function_args)
                            else:
                                logger.opt(exception=True, colors=True).error(
                                    f"ChatHook中遇到了未定义的函数：{function_name}"
                                )
                                continue
                    logger.debug(f"函数{function_name}返回：{func_response}")
                    msg = {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": func_response,
                    }
                    msg_list.append(msg)
        except Exception as e:
            logger.opt(colors=True, exception=e).exception(
                f"ERROR\n{e!s}\n!调用Tools失败！已旧数据继续处理..."
            )
            msg_list = chat_list_backup
    except Exception as e:
        if isinstance(e, ChatException):
            raise
        await bot.send(nonebot_event, "出错了稍后试试吧～")
        logger.opt(exception=e, colors=True).error(
            "<r><bg #f8bbd0>出错了！</bg #f8bbd0></r>"
        )


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
                await write_memory_data(nonebot_event, data)
                await bot.send(
                    nonebot_event,
                    random.choice(config_manager.config.cookies.block_msg),
                )
                posthook.cancel_nonebot_process()
