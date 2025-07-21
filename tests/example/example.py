from nonebot import logger
from nonebot.plugin import require

require("nonebot_plugin_suggarchat")
from nonebot_plugin_suggarchat.event import (
    BeforeChatEvent,
    BeforePokeEvent,
    ChatEvent,
    PokeEvent,
)
from nonebot_plugin_suggarchat.on_event import (
    on_before_chat,
    on_before_poke,
    on_chat,
    on_poke,
)


@on_poke(priority=10).handle()
async def _(event: PokeEvent):
    logger.info("戳了！")
    logger.info(event)


@on_before_poke(priority=10).handle()
async def _(event: BeforePokeEvent):
    logger.info("现在在获取模型的回复之前！")
    logger.info(event)


@on_before_chat(priority=10).handle()
async def _(event: BeforeChatEvent):
    logger.info("现在在获取模型的回复之前！")
    logger.info(event)


@on_chat(priority=10).handle()
async def _(event: ChatEvent):
    logger.info("收到聊天事件!")
    logger.info(event)
