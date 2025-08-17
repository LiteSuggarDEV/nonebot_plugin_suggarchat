from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, MessageSegment
from nonebot.matcher import Matcher

from ..check_rule import is_bot_admin
from ..config import config_manager
from ..utils.memory import get_memory_data


async def insights(
    event: MessageEvent,
    matcher: Matcher,
):
    data = await get_memory_data(event)
    config = config_manager.config
    user_limit = config.usage_limit.user_daily_limit
    user_token_limit = config.usage_limit.user_daily_token_limit
    group_limit = config.usage_limit.group_daily_limit
    group_token_limit = config.usage_limit.group_daily_token_limit
    enable_limit = config.usage_limit.enable_usage_limit
    is_admin = await is_bot_admin(event)

    msg = (
        f"您今日的使用次数为：{data.usage}/{user_limit if (user_limit != -1 and enable_limit and not is_admin) else '♾'}次"
        + f"\n您今日的token使用量为：{data.input_token_usage + data.output_token_usage}/{user_token_limit if (user_token_limit != -1 and enable_limit and not is_admin) else '♾'}token"
    )
    if isinstance(event, GroupMessageEvent):
        msg = (
            f"群组使用次数为：{data.usage}/{group_limit if (group_limit != -1 and enable_limit) else '♾'}次"
            + f"\n群组使用token为：{data.input_token_usage + data.output_token_usage}/{group_token_limit if (group_token_limit != -1 and enable_limit) else '♾'}token"
            + f"\n\n{msg}"
        )
    await matcher.finish(
        MessageSegment.at(event.user_id) + MessageSegment.text(f" {msg}")
    )
