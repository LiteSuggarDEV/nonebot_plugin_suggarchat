import json
import random
import typing
from typing import Any

from amrita_core import (
    PreCompletionEvent,
    on_precompletion,
)
from amrita_core.builtins.consts import BUILTIN_TOOLS_NAME
from amrita_core.types import (
    CONTENT_LIST_TYPE as SEND_MESSAGES,
)
from amrita_core.types import (
    ToolCall,
    UniResponse,
)
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot_plugin_amrita.memory import CachedUserDataRepository

from .config import Config, config_manager
from .utils.admin import send_to_admin
from .utils.libchat import tools_caller
from .utils.llm_tools.builtin_tools import (
    REPORT_TOOL_HIGH,
    REPORT_TOOL_LOW,
    REPORT_TOOL_MEDIUM,
    report,
)
from .utils.preset import resolve_preset
from .utils.sql import get_uni_user_id

checkhook = on_precompletion(1, False)
BUILTIN_TOOLS_NAME.add(REPORT_TOOL_MEDIUM.function.name)


@checkhook.handle()
async def text_check(
    event: PreCompletionEvent, nonebot_event: MessageEvent, nonebot_matcher: Matcher
) -> None:
    config: Config = config_manager.config
    if not config.llm.tools.enable_report:
        checkhook.pass_event()
    logger.info("Content checking in progress......")
    bot = get_bot()
    match config.llm.tools.report_invoke_level:
        case "low":
            tool_list = [REPORT_TOOL_LOW]
        case "medium":
            tool_list = [REPORT_TOOL_MEDIUM]
        case "high":
            tool_list = [REPORT_TOOL_HIGH]
        case _:
            raise ValueError("Invalid report_invoke_level")
    msg: SEND_MESSAGES = event.get_context_messages().unwrap()
    dm = CachedUserDataRepository()
    if (
        config.llm.tools.report_exclude_context
        and config.llm.tools.report_exclude_system_prompt
    ):
        msg = [event.get_context_messages().get_user_query()]
    elif config.llm.tools.report_exclude_system_prompt:
        msg = event.get_context_messages().get_memory()
    elif config.llm.tools.report_exclude_context:
        msg = [
            event.get_context_messages().get_train(),
            event.get_context_messages().get_user_query(),
        ]
    if not msg:
        logger.warning("Message list is empty, skipping content check")
        return
    response: UniResponse[None, list[ToolCall] | None] = await tools_caller(
        msg, tool_list, preset=await resolve_preset()
    )
    if tool_calls := response.tool_calls:
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args: dict[str, Any] = json.loads(tool_call.function.arguments)
            if function_name == REPORT_TOOL_MEDIUM.function.name:
                if not function_args.get("invoke"):
                    return
                await report(
                    event,
                    nonebot_event,
                    function_args,
                    typing.cast(Bot, bot),
                )
                if config_manager.config.llm.tools.report_then_block:
                    data = await dm.get_memory(get_uni_user_id(nonebot_event))
                    data.memory_json.messages = []
                    await dm.update_memory_data(data)
                    await bot.send(
                        nonebot_event,
                        random.choice(config_manager.config.llm.block_msg),
                    )
                    await nonebot_matcher.finish()
            else:
                await send_to_admin(
                    f"[LLM-Report] Detected non-passed tool call: {function_name}, please feedback this issue to the model provider."
                )
