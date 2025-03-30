from nonebot import get_bot
from nonebot.plugin import require

require("nonebot_plugin_suggarchat")
from nonebot_plugin_suggarchat.event import BeforeChatEvent
from nonebot_plugin_suggarchat.matcher import SuggarMatcher
from nonebot_plugin_suggarchat.on_event import (
    on_before_chat,
)


@on_before_chat().handle()
async def _(event: BeforeChatEvent, matcher: SuggarMatcher):
    if event.user_id != 11451419198:
        # 这里模拟不符合条件的场景
        bot = get_bot(self_id=str(event.get_nonebot_event().self_id))
        nbevent = event.get_nonebot_event()
        await bot.send(event=nbevent, message="你没有权限聊天")
        matcher.cancel()
        # 停止Nonebot层的事件处理，也就是直接取消这个事件，后续不会继续运行，也不会获取模型的响应。
