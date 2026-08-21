from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..utils.app import CachedGroupDataRepository


async def _set_auto(event: GroupMessageEvent, matcher: Matcher, on: bool) -> None:
    """开启/关闭自动回复（FakePeople）"""
    repo = CachedGroupDataRepository()
    group_config = await repo.get_group_config(event.group_id)
    group_config.autoreply = on
    await repo.update_group_config(group_config)
    await matcher.send("✅ 已开启自动回复" if on else "已关闭自动回复")


async def switch(
    event: GroupMessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """自动回复（FakePeople）开关：on/off"""
    arg = args.extract_plain_text().strip().lower()
    if arg in ("开启", "on", "启用", "enable", "1"):
        await _set_auto(event, matcher, True)
    elif arg in ("关闭", "off", "禁用", "disable", "0"):
        await _set_auto(event, matcher, False)
    else:
        await matcher.send("请输入开启或关闭")
