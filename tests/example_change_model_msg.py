from nonebot import logger
from nonebot.plugin import require

require("nonebot_plugin_suggarchat")
from nonebot_plugin_suggarchat.event import ChatEvent
from nonebot_plugin_suggarchat.matcher import Matcher
from nonebot_plugin_suggarchat.on_event import (
    on_before_chat,
)


@on_before_chat().handle()
async def _(event: ChatEvent, matcher: Matcher):
    logger.info(f"{event.model_response}")
    # 这里直接对event的模型响应进行修改，会生效。
    event.model_response += "\n对了，收到消息了～"
    logger.info(f"{event.model_response}")
