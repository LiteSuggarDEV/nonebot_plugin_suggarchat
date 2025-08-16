from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..utils.memory import get_memory_data


async def switch(
    event: GroupMessageEvent, matcher: Matcher, bot: Bot, args: Message = CommandArg()
):
    arg = args.extract_plain_text().strip()
    data = await get_memory_data(event)
    if arg in ("开启", "on", "启用", "enable"):
        if not data.fake_people:
            data.fake_people = True
            await data.save(event)
            await matcher.send("开启FakePeople")
        else:
            await matcher.send("已开启")
    elif arg in ("关闭", "off", "禁用", "disable"):
        if data.fake_people:
            data.fake_people = False
            await data.save(event)
            await matcher.send("关闭FakePeople")
        else:
            await matcher.send("已关闭")
    else:
        await matcher.send("请输入开启或关闭")
