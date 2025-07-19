import json

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
)

from ..admin import send_to_admin


async def report(event: MessageEvent, message: str, bot: Bot) -> str:
    logger.warning(f"{event.user_id} 被举报了 ：{message}")
    await send_to_admin(
        f"{'群' + str(event.group_id) if isinstance(event, GroupMessageEvent) else ''}用户{event.get_user_id()}被举报\n"
        + "LLM原因总结：\n"
        + message
        + f"\n原始消息：\n{event.message.extract_plain_text()}",
        bot,
    )
    return json.dumps({"success": True, "message": "举报成功！"})
